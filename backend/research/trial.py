"""The trial (docs/features/06-trial.md): the hypothesis on trial, papers as witnesses.

plan()  → sub-claims + estimate, stored as a 'planned' trial. Nothing heavy has run.
run()   → only for a planned trial the user approved (claimed atomically, once). Streams events while the
          library and the matrix fill in: strategy → papers found → access → records → matrix rows →
          re-reads of papers the fallback model read → verdict.
reanalyse() → the researcher edited the sub-claims: every matrix row is redone against them (records stay),
          then the Judge weighs again.

Papers are processed concurrently; model calls are capped by backend.agents.MODEL_SLOTS.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from backend.agents import ROLE_MODELS, sanitize_log_message
from backend.research import analyst, judge, librarian, reader, store
from backend.research.llm import start_usage

logger = logging.getLogger("ThothTrial")

DEFAULT_PAPERS = 15
ESTIMATE = {
    "label": "Put the hypothesis on trial",
    "scope": f"about {DEFAULT_PAPERS} papers from OpenAlex and Europe PMC; open-access full text where it exists, abstracts otherwise",
    "duration": "5-10 minutes (free-tier rate limits)",
    "model_calls": f"about {2 * DEFAULT_PAPERS + 3}",
}


class NotTrialable(ValueError):
    """The hypothesis names no constructs, so nothing in a paper could count for or against it."""


async def _split(hypothesis: str) -> Dict[str, Any]:
    try:
        return await analyst.subclaims(hypothesis)
    except Exception as exc:
        logger.warning("[trial] sub-claims failed: %s", sanitize_log_message(str(exc)))
        return {"subclaims": [], "ambiguities": []}


# Stop (docs/features/02 § Live work): the researcher asked a running trial to stop. Checked by the run loop,
# which keeps finished rows and marks the rest "not run". In-process, like the run itself.
STOPS: set = set()
FINAL = ("done", "unreadable", "failed", "not_run")


def request_stop(trial_id: str) -> None:
    STOPS.add(trial_id)


def _usage_event(trial_id: str, usage: Dict[str, int]) -> Tuple[str, Dict[str, Any]]:
    papers = store.list_papers(trial_id)
    return "usage", {"found": len(papers), "analysed": sum(p["status"] == "done" for p in papers), **usage}


async def _stop(trial_id: str, tasks: List[asyncio.Task], usage: Dict[str, int]) -> List[Tuple[str, Dict[str, Any]]]:
    """Keep what's done; everything still in flight or queued is marked "not run". No verdict is weighed unasked."""
    for t in tasks:
        if not t.done():
            t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    papers = store.list_papers(trial_id)
    for p in papers:
        if p["status"] not in FINAL:
            store.update_paper(p["paper_id"], status="not_run")
    store.update_trial(trial_id, status="stopped")
    STOPS.discard(trial_id)
    papers = store.list_papers(trial_id)
    return [("stopped", {"trial_id": trial_id, "found": len(papers), "analysed": sum(p["status"] == "done" for p in papers),
                         "not_run": sum(p["status"] == "not_run" for p in papers),
                         "message": "Stopped. Finished rows are kept; the rest were not run. You can weigh what's done."}),
            _usage_event(trial_id, usage)]


async def plan(thread_id: str, hypothesis: str) -> Dict[str, Any]:
    from backend.conversation import projects
    version = projects.version_of(thread_id, hypothesis)
    marks = await projects.markers(thread_id) if version and version == (projects.current_hypothesis(thread_id) or {}).get("version") else None
    if marks and marks.get("checked") and not marks.get("can_go_on_trial"):
        raise NotTrialable("Name what varies first: a trial needs at least two named constructs, e.g. “night-shift work” and “emotional exhaustion”.")
    split = await _split(hypothesis)
    subs = split["subclaims"] or [{"id": 1, "claim": hypothesis, "constructs": [], "relation": "associated_with"}]
    trial_id = store.create_trial(thread_id, hypothesis, subs, hypothesis_version=version)
    return {"trial_id": trial_id, "hypothesis": hypothesis, "subclaims": subs, "ambiguities": split["ambiguities"],
            "estimate": ESTIMATE, "degraded": not split["subclaims"], "hypothesis_version": version,
            "weaknesses": (marks or {}).get("weaknesses", []), "mode": projects.step_mode(thread_id, "subclaims")}


async def remap_plan(trial_id: str, hypothesis: Optional[str] = None) -> Dict[str, Any]:
    """A rival was swapped in: plan a trial of the new hypothesis on the SAME library. The papers and the Reader's
    hypothesis-blind records are copied; only sub-claims, matrix rows and the verdict will be redone (on approval)."""
    from backend.conversation import projects
    src = store.get_trial(trial_id)
    if not src or src["status"] != "complete":
        raise ValueError("only a finished trial's library can be reused")
    cur = projects.current_hypothesis(src["thread_id"])
    hypothesis = (hypothesis or (cur or {}).get("text") or "").strip()
    if not hypothesis or hypothesis == src["hypothesis"]:
        raise ValueError("the hypothesis is unchanged; use “Weigh again” or “Edit sub-claims” instead")
    split = await _split(hypothesis)
    subs = split["subclaims"] or [{"id": 1, "claim": hypothesis, "constructs": [], "relation": "associated_with"}]
    new_id = store.create_trial(src["thread_id"], hypothesis, subs, hypothesis_version=projects.version_of(src["thread_id"], hypothesis),
                                remapped_from=trial_id)
    store.update_trial(new_id, strategy_json=src["strategy"], adjacent_json=src["adjacent"])
    done = [p for p in src["papers"] if p["status"] == "done"]
    for p in done:
        pid = store.add_paper(new_id, p["meta"])
        # The researcher's "I say" was about the old hypothesis, so it is not carried over.
        store.update_paper(pid, access=p["access"], text_source=p["text_source"], record_json=p["record"], weight=p["weight"], status="read")
    n = len(done)
    papers = f"{n} paper{'' if n == 1 else 's'}"
    return {"trial_id": new_id, "hypothesis": hypothesis, "subclaims": subs, "ambiguities": split["ambiguities"],
            "remapped_from": trial_id, "papers": n, "degraded": not split["subclaims"],
            "estimate": {"label": "Re-map the library to the new hypothesis",
                         "scope": f"the same {papers}; their records are reused, nothing is searched or read again",
                         "duration": "1-3 minutes (free-tier rate limits)", "model_calls": f"about {n + 1}"}}


async def _run_remap(trial: Dict[str, Any], subs: List[Dict[str, Any]]) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    """Rows and verdict for a re-mapped trial: the copied records are analysed against the new sub-claims."""
    trial_id = trial["trial_id"]
    yield "trial_start", {"trial_id": trial_id, "hypothesis": trial["hypothesis"], "subclaims": subs, "remapped_from": trial["remapped_from"]}
    papers = [p for p in store.list_papers(trial_id) if p["status"] == "read"]
    for p in papers:
        yield "paper_found", {"paper_id": p["paper_id"], "meta": p["meta"]}
        yield "paper_access", {"paper_id": p["paper_id"], "access": p["access"], "text_source": p["text_source"]}
        yield "paper_read", {"paper_id": p["paper_id"], "record": p["record"]}

    async def one(p: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        try:
            row = await analyst.row(trial["hypothesis"], subs, p["record"])
        except Exception as exc:
            logger.warning("[trial] re-map row %s failed: %s", p["paper_id"], sanitize_log_message(str(exc)))
            store.update_paper(p["paper_id"], status="failed")
            return "paper_failed", {"paper_id": p["paper_id"], "reason": "This row couldn't be analysed (model error)."}
        store.update_paper(p["paper_id"], row_json=row, status="done")
        return "matrix_row", {"paper_id": p["paper_id"], "row": row, "weight": p["weight"]}

    for task in asyncio.as_completed([one(p) for p in papers]):
        yield await task
    yield "judging", {"witnesses": sum(1 for p in store.list_papers(trial_id) if p["status"] == "done")}
    verdict = await _verdict(trial, trial.get("adjacent") or {"ran": False})
    store.update_trial(trial_id, verdict_json=verdict, status="complete")
    yield "verdict", verdict
    yield "trial_complete", {"trial_id": trial_id, "status": "complete"}


def _clean_subclaims(edited: Optional[List[Any]], fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not edited:
        return fallback
    out = []
    for item in edited:
        claim = (item.get("claim") if isinstance(item, dict) else str(item) or "").strip()
        if claim:
            out.append({"id": len(out) + 1, "claim": claim, "constructs": item.get("constructs", []) if isinstance(item, dict) else [],
                        "relation": item.get("relation", "associated_with") if isinstance(item, dict) else "associated_with"})
    return out[:6] or fallback


async def _process(trial: Dict[str, Any], paper_id: str, meta: Dict[str, Any], out: asyncio.Queue,
                   text_override: Optional[Tuple[str, str, str]] = None, texts: Optional[Dict[str, str]] = None) -> None:
    """Fetch → read (hypothesis-blind) → analyse one paper, reporting each step."""
    try:
        text, access, source = text_override or await librarian.full_text(meta)
        if texts is not None:
            texts[paper_id] = text
        store.update_paper(paper_id, access=access, text_source=source, status="reading")
        await out.put(("paper_access", {"paper_id": paper_id, "access": access, "text_source": source}))
        if access == "metadata_only":
            store.update_paper(paper_id, status="unreadable")
            await out.put(("paper_skipped", {"paper_id": paper_id, "reason": "Only the title is available; nothing to read."}))
            return
        record = await reader.read(meta, text, access)
        store.update_paper(paper_id, record_json=record, status="analysing")
        await out.put(("paper_read", {"paper_id": paper_id, "record": record}))
        row = await analyst.row(trial["hypothesis"], trial["subclaims"], record)
        w = analyst.weight(record)
        store.update_paper(paper_id, row_json=row, weight=w, status="done")
        await out.put(("matrix_row", {"paper_id": paper_id, "row": row, "weight": w}))
    except Exception as exc:
        logger.warning("[trial] paper %s failed: %s", paper_id, sanitize_log_message(str(exc)))
        store.update_paper(paper_id, status="failed")
        await out.put(("paper_failed", {"paper_id": paper_id, "reason": "This paper couldn't be read or analysed (model or network error)."}))


async def _reread_one(trial: Dict[str, Any], paper: Dict[str, Any], text: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Re-read one paper with the primary model only. If that fails too, the old record and its flag stay."""
    pid, old_by = paper["paper_id"], paper["record"].get("read_by")
    try:
        record = await reader.read(paper["meta"], text, paper["access"], primary_only=True)
        # A primary-only call cannot be answered by the fallback, so an unnamed server is the primary model.
        record["read_by"] = record.get("read_by") or ROLE_MODELS["reader"]["model"]
        if reader.read_by_fallback(record):
            raise RuntimeError("the re-read was not served by the primary model")
        row = await analyst.row(trial["hypothesis"], trial["subclaims"], record)
    except Exception as exc:
        logger.info("[trial] re-read of %s kept the fallback record: %s", pid, sanitize_log_message(str(exc)))
        return [("paper_reread", {"paper_id": pid, "recovered": False, "read_by": old_by,
                                  "message": "The primary model was still unavailable; the fallback reading stays flagged."})]
    w = analyst.weight(record)
    store.update_paper(pid, record_json=record, row_json=row, weight=w, status="done")
    return [("paper_reread", {"paper_id": pid, "recovered": True, "read_by": record["read_by"], "was_read_by": old_by, "record": record}),
            ("matrix_row", {"paper_id": pid, "row": row, "weight": w})]


async def reread_fallbacks(trial: Dict[str, Any], texts: Dict[str, str]) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    """After the main pass: papers the fallback model read (during a 429) are read again by the primary."""
    flagged = [p for p in store.list_papers(trial["trial_id"])
               if p["status"] == "done" and reader.read_by_fallback(p["record"]) and texts.get(p["paper_id"])]
    if not flagged:
        return
    yield "rereading", {"papers": [p["paper_id"] for p in flagged]}
    for events in await asyncio.gather(*[_reread_one(trial, p, texts[p["paper_id"]]) for p in flagged]):
        for ev in events:
            yield ev


async def _verdict(trial: Dict[str, Any], adjacent: Dict[str, Any]) -> Dict[str, Any]:
    papers = [p for p in store.list_papers(trial["trial_id"]) if p["status"] == "done"]
    if not papers:
        return {"overall": {"verdict": "insufficient_evidence", "reason": "No paper could be read and analysed, so there is nothing to weigh."},
                "per_subclaim": [], "originality": {"label": "insufficiently_assessed", "reason": ""}, "gaps": [],
                "witnesses": 0, "full_text_witnesses": 0, "guardrail_notes": [], "degraded": True}
    not_run = sum(1 for p in store.list_papers(trial["trial_id"]) if p["status"] == "not_run")
    try:
        verdict = await judge.judge(trial["hypothesis"], trial["subclaims"], papers, adjacent)
        if not_run:
            verdict["guardrail_notes"] = verdict.get("guardrail_notes", []) + [
                f"{not_run} papers were not run (the trial was stopped); this verdict weighs only the {len(papers)} that were."]
            verdict["partial"] = True
        return verdict
    except Exception as exc:
        logger.warning("[trial] judge failed: %s", sanitize_log_message(str(exc)))
        return {"overall": {"verdict": "insufficient_evidence", "reason": "The judge couldn't be reached; the matrix stands without a verdict."},
                "per_subclaim": [], "originality": {"label": "insufficiently_assessed", "reason": ""}, "gaps": [],
                "witnesses": len(papers), "full_text_witnesses": sum(p["access"] == "full_text" for p in papers),
                "guardrail_notes": [], "degraded": True}


async def run(trial_id: str, edited_subclaims: Optional[List[Any]] = None, limit: int = DEFAULT_PAPERS) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    trial = store.get_trial(trial_id)
    if trial is None:
        yield "error", {"error": "No such trial."}
        return
    subs = _clean_subclaims(edited_subclaims, trial["subclaims"])
    if not store.claim_for_run(trial_id):
        yield "error", {"error": f"This trial is {trial['status']}; only a planned trial you approve can run, and only once."}
        return
    store.update_trial(trial_id, subclaims_json=subs)
    trial = {**trial, "subclaims": subs}
    STOPS.discard(trial_id)
    usage = start_usage()
    if trial.get("remapped_from"):
        try:
            async for ev in _run_remap(trial, subs):
                yield ev
        except asyncio.CancelledError:
            store.update_trial(trial_id, status="stopped")
            raise
        return
    try:
        yield "trial_start", {"trial_id": trial_id, "hypothesis": trial["hypothesis"], "subclaims": subs}

        strat = await librarian.strategy(trial["hypothesis"])
        store.update_trial(trial_id, strategy_json=strat)
        yield "strategy", {"queries": strat["queries"], "adjacent_fields": strat.get("adjacent_fields", []), "degraded": strat.get("degraded", False)}

        adjacent_task = asyncio.create_task(librarian.adjacent_search(strat))
        found = await librarian.search(strat, limit, [sc["claim"] for sc in subs])
        if trial_id in STOPS:
            for ev in await _stop(trial_id, [adjacent_task], usage):
                yield ev
            return
        store.update_trial(trial_id, strategy_json=strat)
        off = strat.get("europepmc_dropped_off_topic") or {}
        if off.get("count"):
            yield "search_filtered", {"dropped": off["count"], "titles": off.get("titles", []),
                                      "reason": "Europe PMC results whose title and abstract shared too few words with the search"}
        ids = []
        for meta in found:
            pid = store.add_paper(trial_id, meta)
            ids.append((pid, meta))
            yield "paper_found", {"paper_id": pid, "meta": meta}
        if not found:
            yield "notice", {"message": "The searches returned no papers."}

        q: asyncio.Queue = asyncio.Queue()
        texts: Dict[str, str] = {}
        workers = [asyncio.create_task(_process(trial, pid, meta, q, texts=texts)) for pid, meta in ids]
        pending = len(workers)
        finals = {"matrix_row", "paper_skipped", "paper_failed"}
        yield _usage_event(trial_id, usage)
        while pending:
            if trial_id in STOPS:
                for ev in await _stop(trial_id, workers + [adjacent_task], usage):
                    yield ev
                return
            try:
                name, payload = await asyncio.wait_for(q.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if name in finals:
                pending -= 1
            yield name, payload
            if name in finals:
                yield _usage_event(trial_id, usage)

        async for ev in reread_fallbacks(trial, texts):
            yield ev
        if trial_id in STOPS:
            for ev in await _stop(trial_id, [adjacent_task], usage):
                yield ev
            return

        adjacent = await adjacent_task
        store.update_trial(trial_id, adjacent_json=adjacent)
        yield "adjacent", {"ran": adjacent.get("ran", False), "fields": [{"field": f["field"], "papers": len(f["papers"])} for f in adjacent.get("fields", [])]}
        yield "judging", {"witnesses": sum(1 for p in store.list_papers(trial_id) if p["status"] == "done")}

        verdict = await _verdict(trial, adjacent)
        store.update_trial(trial_id, verdict_json=verdict, status="complete")
        yield _usage_event(trial_id, usage)
        yield "verdict", verdict
        yield "trial_complete", {"trial_id": trial_id, "status": "complete"}
    except asyncio.CancelledError:
        # The page was closed mid-run: the same as Stop (finished rows kept, the rest "not run").
        store.update_trial(trial_id, status="stopped")
        for t in [t for t in locals().get("workers", []) if not t.done()]:
            t.cancel()
        for p in store.list_papers(trial_id):
            if p["status"] not in FINAL:
                store.update_paper(p["paper_id"], status="not_run")
        STOPS.discard(trial_id)
        raise


async def add_by_doi(trial_id: str, doi: str) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    trial = store.get_trial(trial_id)
    meta = await librarian.by_doi(doi) if trial else None
    if not meta:
        yield "error", {"error": "That DOI couldn't be found."}
        return
    pid = store.add_paper(trial_id, meta)
    yield "paper_found", {"paper_id": pid, "meta": meta}
    q: asyncio.Queue = asyncio.Queue()
    await _process(trial, pid, meta, q)
    while not q.empty():
        yield await q.get()


async def complete_with_pdf(paper_id: str, pdf_base64: str) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    """'Upload PDF to complete': re-read and re-analyse one paper from the user's own copy."""
    paper = store.get_paper(paper_id)
    if not paper:
        yield "error", {"error": "No such paper."}
        return
    try:
        text = librarian.pdf_to_text(base64.b64decode(pdf_base64))
    except Exception:
        text = ""
    if len(text) < 1000:
        yield "error", {"error": "That PDF had no readable text (scanned images can't be read yet)."}
        return
    trial = store.get_trial(paper["trial_id"])
    q: asyncio.Queue = asyncio.Queue()
    await _process(trial, paper_id, paper["meta"], q, text_override=(text, "full_text", "Your uploaded PDF"))
    while not q.empty():
        yield await q.get()


async def rejudge(trial_id: str) -> Dict[str, Any]:
    trial = store.get_trial(trial_id)
    verdict = await _verdict(trial, trial.get("adjacent") or {"ran": False})
    store.update_trial(trial_id, verdict_json=verdict)
    return verdict


async def reanalyse(trial_id: str, edited_subclaims: List[Any]) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    """The researcher changed what the hypothesis is made of: redo every matrix row against the new sub-claims
    (the hypothesis-blind records stay; the Reader doesn't run), then weigh again."""
    trial = store.get_trial(trial_id)
    if trial is None:
        yield "error", {"error": "No such trial."}
        return
    subs = _clean_subclaims(edited_subclaims, [])
    if not subs:
        yield "error", {"error": "Give at least one sub-claim."}
        return
    if not store.claim_for_reanalysis(trial_id):
        yield "error", {"error": f"This trial is {trial['status']}; only a finished trial can be re-analysed."}
        return
    try:
        store.update_trial(trial_id, subclaims_json=subs)
        trial = {**trial, "subclaims": subs}
        yield "subclaims_updated", {"trial_id": trial_id, "subclaims": subs}
        done = [p for p in store.list_papers(trial_id) if p["status"] == "done"]

        async def one(p: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
            try:
                row = await analyst.row(trial["hypothesis"], subs, p["record"])
            except Exception as exc:
                logger.warning("[trial] re-analysis of %s failed: %s", p["paper_id"], sanitize_log_message(str(exc)))
                # The old row answers different sub-claims; keeping it would mislead.
                row = {"per_subclaim": [], "stance": "unknown", "i_say_draft": "This row couldn't be redone for the edited sub-claims."}
                store.update_paper(p["paper_id"], row_json=row)
                return "row_failed", {"paper_id": p["paper_id"], "row": row}
            store.update_paper(p["paper_id"], row_json=row)
            return "matrix_row", {"paper_id": p["paper_id"], "row": row, "weight": p["weight"]}

        for task in asyncio.as_completed([one(p) for p in done]):
            yield await task
        yield "judging", {"witnesses": len(done)}
        verdict = await _verdict(trial, trial.get("adjacent") or {"ran": False})
        store.update_trial(trial_id, verdict_json=verdict)
        yield "verdict", verdict
    finally:
        store.update_trial(trial_id, status="complete")
    yield "trial_complete", {"trial_id": trial_id, "status": "complete"}
