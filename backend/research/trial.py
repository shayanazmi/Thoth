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

logger = logging.getLogger("ThothTrial")

DEFAULT_PAPERS = 15
ESTIMATE = {
    "label": "Put the hypothesis on trial",
    "scope": f"about {DEFAULT_PAPERS} papers from OpenAlex and Europe PMC; open-access full text where it exists, abstracts otherwise",
    "duration": "5-10 minutes (free-tier rate limits)",
    "model_calls": f"about {2 * DEFAULT_PAPERS + 3}",
}


async def plan(thread_id: str, hypothesis: str) -> Dict[str, Any]:
    try:
        split = await analyst.subclaims(hypothesis)
    except Exception as exc:
        logger.warning("[trial] sub-claims failed: %s", sanitize_log_message(str(exc)))
        split = {"subclaims": [], "ambiguities": []}
    subs = split["subclaims"] or [{"id": 1, "claim": hypothesis, "constructs": [], "relation": "associated_with"}]
    trial_id = store.create_trial(thread_id, hypothesis, subs)
    return {"trial_id": trial_id, "hypothesis": hypothesis, "subclaims": subs, "ambiguities": split["ambiguities"],
            "estimate": ESTIMATE, "degraded": not split["subclaims"]}


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
    try:
        return await judge.judge(trial["hypothesis"], trial["subclaims"], papers, adjacent)
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
    try:
        yield "trial_start", {"trial_id": trial_id, "hypothesis": trial["hypothesis"], "subclaims": subs}

        strat = await librarian.strategy(trial["hypothesis"])
        store.update_trial(trial_id, strategy_json=strat)
        yield "strategy", {"queries": strat["queries"], "adjacent_fields": strat.get("adjacent_fields", []), "degraded": strat.get("degraded", False)}

        adjacent_task = asyncio.create_task(librarian.adjacent_search(strat))
        found = await librarian.search(strat, limit, [sc["claim"] for sc in subs])
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
        while pending:
            name, payload = await q.get()
            if name in finals:
                pending -= 1
            yield name, payload

        async for ev in reread_fallbacks(trial, texts):
            yield ev

        adjacent = await adjacent_task
        store.update_trial(trial_id, adjacent_json=adjacent)
        yield "adjacent", {"ran": adjacent.get("ran", False), "fields": [{"field": f["field"], "papers": len(f["papers"])} for f in adjacent.get("fields", [])]}
        yield "judging", {"witnesses": sum(1 for p in store.list_papers(trial_id) if p["status"] == "done")}

        verdict = await _verdict(trial, adjacent)
        store.update_trial(trial_id, verdict_json=verdict, status="complete")
        yield "verdict", verdict
        yield "trial_complete", {"trial_id": trial_id, "status": "complete"}
    except asyncio.CancelledError:
        store.update_trial(trial_id, status="stopped")
        for t in [t for t in locals().get("workers", []) if not t.done()]:
            t.cancel()
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
