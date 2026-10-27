"""Systematic review (docs/features/05-literature.md tier 3; prompts in 09 § Librarian protocol, § Screener).

A protocol the researcher approves → identification (both databases, duplicates counted, not hidden) →
title/abstract screening → full-text retrieval and screening → included studies become a linked trial
(records, matrix rows, verdict). Two modes, chosen per review:
  copilot  the run pauses at each screening stage until the researcher has confirmed every decision;
  auto     decisions apply; low-confidence ones (< 0.7) are queued for audit without blocking.
PRISMA 2020 counts are computed only from stored records, after every change. Nothing is decided on the
model's behalf: if the Screener cannot be reached, records stay "unscreened" and the run stops there.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx

from backend.agents import sanitize_log_message
from backend.research import analyst, librarian, reader, store, trial as trial_mod
from backend.research import review_store as rs
from backend.research.llm import call_json

IDENT_LIMIT = 25          # per database
TA_BATCH = 4              # records per Screener call at title/abstract stage
AUDIT_BELOW = 0.7         # Auto mode: decisions below this confidence are queued for the researcher
FT_TEXT_CHARS = 6000      # focused full text given to the Screener
CRITERIA = ("population", "exposure", "comparison", "outcomes", "designs", "dates", "languages")

ESTIMATE = {
    "label": "Systematic review (PRISMA 2020)",
    "scope": f"up to {2 * IDENT_LIMIT} records from OpenAlex and Europe PMC, screened against your protocol; included studies read in full and weighed",
    "duration": "15-40 minutes on the free tier (plus your screening time in Human-in-the-loop mode)",
    "model_calls": "about 15-40",
}

PROTOCOL_PROMPT = """ROLE
You are Thoth's Librarian. Draft a systematic-review protocol for the question below. The researcher will
review and edit it before anything runs.

From the question, draft:
- the question in PICO (intervention/exposure) or PEO (experience) form;
- eligibility criteria, each checkable from a title, abstract or methods section;
- databases (OpenAlex and Europe PMC are available) and one search string for each: a keyword string of at
  most 10 words for OpenAlex, and a Boolean string for Europe PMC with AT MOST THREE concept blocks
  (population/exposure and outcome first; never AND the comparison group or a mechanism as its own block).

OUTPUT (JSON)
{"framework": "PICO"|"PEO",
 "question": {"population": str, "exposure": str, "comparison": str, "outcome": str},
 "eligibility": {"population": str, "exposure": str, "comparison": str, "outcomes": str,
                 "designs": str, "dates": str, "languages": str},
 "search": {"openalex": str, "europepmc": str},
 "notes": str}

RULES
- Each criterion is one or two plain sentences a screener can apply to a single record, and covers ONE thing:
  the exposure criterion describes the exposure only (never the comparison group), the comparison criterion
  describes the comparison only, the outcome criterion the outcome only. Overlapping criteria make one edit
  ineffective and double-count exclusions.
- Do not encode the expected result of the study in any criterion: screen on what was studied, never on what was found."""

SCREENER_PROMPT = """ROLE
You are Thoth's Screener for a systematic review. Apply the approved protocol to each record. You check
eligibility, not quality or results.

METHOD
1. For each eligibility criterion, decide yes / no / unclear, quoting at most 15 words of the record that decide it.
2. Title/abstract stage: exclude only if a criterion is clearly not met; when unsure choose "maybe".
3. Full-text stage: include only if every criterion is met; otherwise exclude with the FIRST failed criterion.
   "maybe" is not allowed at full-text stage.
4. The exclusion reason must be one criterion name: population, exposure, comparison, outcomes, designs, dates, languages.

OUTPUT (JSON)
{"decisions": [{"record_id": str, "decision": "include"|"exclude"|"maybe",
   "criteria": [{"criterion": str, "met": "yes"|"no"|"unclear", "evidence": str}],
   "exclusion_reason": str, "confidence": number}]}

RULES
- Never exclude because a result is inconvenient, small or null.
- Decide every record you are given, using its record_id exactly."""


# ---------------------------------------------------------------- protocol

def _clean_protocol(p: Dict[str, Any], question: str) -> Dict[str, Any]:
    elig = p.get("eligibility") if isinstance(p.get("eligibility"), dict) else {}
    search = p.get("search") if isinstance(p.get("search"), dict) else {}
    kw = librarian.keywords(question)
    return {
        "framework": p.get("framework") if p.get("framework") in ("PICO", "PEO") else "PICO",
        "question": p.get("question") if isinstance(p.get("question"), dict) else {},
        "eligibility": {c: str(elig.get(c) or "").strip() for c in CRITERIA},
        "search": {"openalex": librarian.keywords(search.get("openalex") or kw, 12), "europepmc": str(search.get("europepmc") or kw)},
        "notes": str(p.get("notes") or ""),
    }


async def draft_protocol(thread_id: str, hypothesis: str, question: str = "") -> Dict[str, Any]:
    q = question or hypothesis
    try:
        raw = await call_json("librarian", PROTOCOL_PROMPT, f"<question>{q}</question>", default={}) or {}
        degraded = not (isinstance(raw, dict) and raw.get("eligibility"))
    except Exception as exc:
        logging.getLogger("ThothReview").warning("[review] protocol draft failed: %s", sanitize_log_message(str(exc)))
        raw, degraded = {}, True
    protocol = _clean_protocol(raw if isinstance(raw, dict) else {}, q)
    try:
        subclaims = (await analyst.subclaims(hypothesis))["subclaims"]
    except Exception:
        subclaims = []
    subclaims = subclaims or [{"id": 1, "claim": hypothesis, "constructs": [], "relation": "associated_with"}]
    rid = rs.create(thread_id, hypothesis, protocol, subclaims)
    return {"review_id": rid, "hypothesis": hypothesis, "protocol": protocol, "subclaims": subclaims,
            "estimate": ESTIMATE, "degraded": degraded}


# ---------------------------------------------------------------- counts

def _final(rec: Dict[str, Any], stage: str) -> Optional[Dict[str, Any]]:
    return (rec.get("screening") or {}).get(stage)


def prisma_counts(review_id: str) -> Dict[str, Any]:
    """PRISMA 2020 flow, computed only from stored records."""
    recs = rs.records(review_id)
    by_source = Counter(r["source"] for r in recs)
    dups = [r for r in recs if r["dup_of"]]
    screened = [r for r in recs if not r["dup_of"]]
    ta = [(r, _final(r, "ta")) for r in screened]
    ta_excluded = [r for r, d in ta if d and d["decision"] == "exclude"]
    unscreened = [r for r, d in ta if not d or d["decision"] == "unscreened"]
    sought = [r for r, d in ta if d and d["decision"] in ("include", "maybe")]
    not_retrieved = [r for r in sought if r["ft_access"] in ("abstract_only", "metadata_only")]
    assessed = [r for r in sought if r["ft_access"] == "full_text"]
    ft = [(r, _final(r, "ft")) for r in assessed]
    ft_excluded = [(r, d) for r, d in ft if d and d["decision"] == "exclude"]
    ft_unscreened = [r for r, d in ft if not d or d["decision"] == "unscreened"]
    included = [r for r, d in ft if d and d["decision"] == "include"]
    return {
        "identified": len(recs), "by_source": dict(by_source), "duplicates_removed": len(dups),
        "screened": len(screened), "excluded_title_abstract": len(ta_excluded),
        "excluded_title_abstract_reasons": dict(Counter(_final(r, "ta").get("reason") or "unspecified" for r in ta_excluded)),
        "unscreened": len(unscreened),
        "sought_for_retrieval": len(sought), "not_retrieved": len(not_retrieved),
        "awaiting_retrieval": len([r for r in sought if not r["ft_access"]]),
        "assessed_full_text": len(assessed),
        "excluded_full_text": len(ft_excluded),
        "excluded_full_text_reasons": dict(Counter(d.get("reason") or "unspecified" for _, d in ft_excluded)),
        "full_text_unscreened": len(ft_unscreened),
        "included": len(included),
    }


# ---------------------------------------------------------------- screening

def _enforce(d: Dict[str, Any], stage: str, mode: str) -> Dict[str, Any]:
    decision = d.get("decision") if d.get("decision") in ("include", "exclude", "maybe") else "maybe"
    reason = str(d.get("exclusion_reason") or "").strip().lower()
    try:
        conf = max(0.0, min(1.0, float(d.get("confidence"))))
    except Exception:
        conf = 0.0
    note = ""
    if decision == "exclude" and reason not in CRITERIA:
        # Every exclusion carries one protocol reason; without one it isn't a valid exclusion.
        decision, conf, note = ("maybe" if stage == "ta" else "exclude"), min(conf, 0.3), "exclusion without a protocol reason"
        reason = "" if stage == "ta" else "unspecified"
    if stage == "ft" and decision == "maybe":
        decision, conf, note = "exclude", min(conf, 0.3), "full-text screening cannot say 'maybe'"
        reason = reason if reason in CRITERIA else "unspecified"
    return {"decision": decision, "reason": reason if decision == "exclude" else "", "confidence": conf,
            "criteria": [c for c in d.get("criteria") or [] if isinstance(c, dict)][:7],
            "by": "screener", "screener_decision": decision, "note": note,
            "needs_review": mode == "copilot" or conf < AUDIT_BELOW or bool(note)}


async def _screen(protocol: Dict[str, Any], items: List[Tuple[Dict[str, Any], str]], stage: str, mode: str) -> Dict[str, Dict[str, Any]]:
    """items: (record, text). Returns record_id → decision. Records the Screener didn't decide are absent."""
    human = (f"<protocol>{json.dumps(protocol['eligibility'])}</protocol>\n<stage>{'title_abstract' if stage == 'ta' else 'full_text'}</stage>\n"
             + "\n".join(f"<untrusted record_id=\"{r['record_id']}\">\n{text}\n</untrusted>" for r, text in items))
    raw = await call_json("screener", SCREENER_PROMPT, human, default={}) or {}
    wanted = {r["record_id"] for r, _ in items}
    return {d["record_id"]: _enforce(d, stage, mode) for d in (raw.get("decisions") or [])
            if isinstance(d, dict) and d.get("record_id") in wanted}


def _ta_text(r: Dict[str, Any]) -> str:
    m = r["meta"]
    return f"Title: {m.get('title')}\nYear: {m.get('year')}\nVenue: {m.get('venue') or ''}\nAbstract: {m.get('abstract') or '(no abstract)'}"


def queue(review_id: str, stage: str) -> List[Dict[str, Any]]:
    """Decisions the researcher still has to look at for this stage."""
    out = []
    for r in rs.records(review_id):
        d = _final(r, stage)
        if r["dup_of"] or not d or d.get("by") == "user":
            continue
        if stage == "ft" and r["ft_access"] != "full_text":
            continue
        if d.get("needs_review"):
            out.append({"record_id": r["record_id"], "meta": {k: r["meta"].get(k) for k in ("title", "year", "venue", "abstract", "url")},
                        "decision": d})
    return out


def decide(record_id: str, stage: str, decision: str, reason: str = "") -> Dict[str, Any]:
    """The researcher confirms or overrides a decision. Exclusions need a protocol reason."""
    rec = rs.get_record(record_id)
    if not rec or stage not in ("ta", "ft"):
        raise KeyError(record_id)
    allowed = ("include", "exclude", "maybe") if stage == "ta" else ("include", "exclude")
    reason = (reason or "").strip().lower()
    if decision not in allowed or (decision == "exclude" and reason not in CRITERIA):
        raise ValueError("decision must be one of %s; an exclusion needs one protocol criterion as its reason" % (allowed,))
    prev = _final(rec, stage) or {}
    screening = dict(rec["screening"])
    screening[stage] = {**prev, "decision": decision, "reason": reason if decision == "exclude" else "", "by": "user",
                        "overridden": bool(prev) and prev.get("screener_decision") != decision, "needs_review": False}
    if stage == "ta" and decision == "exclude":
        screening.pop("ft", None)
    rs.update_record(record_id, screening_json=screening)
    return {"record_id": record_id, "stage": stage, **screening[stage]}


def accept_all(review_id: str, stage: str) -> int:
    """Confirm every remaining Screener decision for this stage as the researcher's own."""
    n = 0
    for item in queue(review_id, stage):
        d = item["decision"]
        decide(item["record_id"], stage, d["decision"], d.get("reason") or "")
        n += 1
    return n


# ---------------------------------------------------------------- the run

async def _identify(rev: Dict[str, Any]) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    p = rev["protocol"]["search"]
    async with httpx.AsyncClient(timeout=20, headers=librarian.UA, follow_redirects=True) as client:
        oa, epmc = await asyncio.gather(librarian.search_openalex(client, p["openalex"], IDENT_LIMIT),
                                        librarian.search_europepmc(client, p["europepmc"], IDENT_LIMIT))
        if len(epmc) < 3:
            epmc += await librarian.search_europepmc(client, librarian.keywords(p["openalex"], 8), IDENT_LIMIT)
    seen: Dict[str, str] = {}
    for meta in oa + epmc:
        if not meta.get("title"):
            continue
        keys = [k for k in ((meta.get("doi") or "").lower(), librarian._norm_title(meta["title"])) if k]
        dup = next((seen[k] for k in keys if k in seen), None)
        rid = rs.add_record(rev["review_id"], meta, meta.get("found_via", ""), dup)
        for k in keys:
            seen.setdefault(k, rid)
    yield "counts", prisma_counts(rev["review_id"])


async def advance(review_id: str) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    """Run from wherever the review is until it pauses for the researcher, is blocked, or completes.
    Every step only processes records that still lack its result, so it is safe to call again."""
    rev = rs.get(review_id)
    mode = rev["mode"]
    if rev["stage"] in ("planned", "identifying"):
        rs.update(review_id, stage="identifying")
        async for ev in _identify(rev):
            yield ev
        rs.update(review_id, stage="screening_ta")

    # Title/abstract screening, in batches.
    todo = [r for r in rs.records(review_id) if not r["dup_of"] and not _final(r, "ta")]
    for i in range(0, len(todo), TA_BATCH):
        batch = todo[i:i + TA_BATCH]
        try:
            got = await _screen(rev["protocol"], [(r, _ta_text(r)) for r in batch], "ta", mode)
        except Exception as exc:
            logging.getLogger("ThothReview").warning("[review] screener failed: %s", sanitize_log_message(str(exc)))
            got = {}
        missing = [r for r in batch if r["record_id"] not in got]
        for r in missing if got else []:
            # A batch answer can be cut short; try the records it missed one at a time before giving up.
            try:
                got.update(await _screen(rev["protocol"], [(r, _ta_text(r))], "ta", mode))
            except Exception:
                pass
        if not got or any(r["record_id"] not in got for r in batch):
            for r in batch:
                if r["record_id"] in got:
                    rs.update_record(r["record_id"], screening_json={**r["screening"], "ta": got[r["record_id"]]})
                else:
                    rs.update_record(r["record_id"], screening_json={**r["screening"], "ta": {"decision": "unscreened", "by": "nobody"}})
            rs.update(review_id, status="blocked", note="The Screener couldn't be reached or returned no decision for some records; they stay unscreened. Nothing was decided on its behalf.")
            yield "counts", prisma_counts(review_id)
            yield "blocked", {"stage": "ta", "reason": rs.get(review_id)["note"]}
            return
        for r in batch:
            if r["record_id"] in got:
                rs.update_record(r["record_id"], screening_json={**r["screening"], "ta": got[r["record_id"]]})
        yield "screening_progress", {"stage": "ta", "done": min(i + TA_BATCH, len(todo)), "total": len(todo)}
        yield "counts", prisma_counts(review_id)
    if mode == "copilot" and queue(review_id, "ta"):
        rs.update(review_id, status="awaiting_researcher", stage="screening_ta")
        yield "paused", {"stage": "ta", "queue": queue(review_id, "ta")}
        return

    # Full-text retrieval for everything that passed title/abstract screening.
    rs.update(review_id, status="running", stage="retrieving")
    texts: Dict[str, str] = {}
    sought = [r for r in rs.records(review_id) if not r["dup_of"] and (_final(r, "ta") or {}).get("decision") in ("include", "maybe")]
    for r in sought:
        if r["ft_access"]:
            continue
        text, access, _src = await librarian.full_text(r["meta"])
        rs.update_record(r["record_id"], ft_access=access)
        if access == "full_text":
            texts[r["record_id"]] = text
        yield "retrieved", {"record_id": r["record_id"], "access": access}
    yield "counts", prisma_counts(review_id)

    # Full-text screening, one record per call.
    rs.update(review_id, stage="screening_ft")
    for r in [x for x in rs.records(review_id) if x["ft_access"] == "full_text" and not _final(x, "ft")
              and (_final(x, "ta") or {}).get("decision") in ("include", "maybe")]:
        text = texts.get(r["record_id"])
        if text is None:
            text, _a, _s = await librarian.full_text(r["meta"])
        try:
            got = await _screen(rev["protocol"], [(r, reader.focus(text, FT_TEXT_CHARS))], "ft", mode)
        except Exception:
            got = {}
        if r["record_id"] not in got:
            rs.update_record(r["record_id"], screening_json={**r["screening"], "ft": {"decision": "unscreened", "by": "nobody"}})
            rs.update(review_id, status="blocked", note="The Screener couldn't be reached at full-text stage; nothing was decided on its behalf.")
            yield "counts", prisma_counts(review_id)
            yield "blocked", {"stage": "ft", "reason": rs.get(review_id)["note"]}
            return
        rs.update_record(r["record_id"], screening_json={**r["screening"], "ft": got[r["record_id"]]})
        yield "counts", prisma_counts(review_id)
    if mode == "copilot" and queue(review_id, "ft"):
        rs.update(review_id, status="awaiting_researcher", stage="screening_ft")
        yield "paused", {"stage": "ft", "queue": queue(review_id, "ft")}
        return

    # Included studies → a linked trial: read, analysed, weighed.
    rs.update(review_id, status="running", stage="synthesis")
    rev = rs.get(review_id)
    c = prisma_counts(review_id)
    if c["included"] == 0 and not rev["trial_id"]:
        # A strict protocol can include nothing. Say so plainly; don't create an empty trial.
        rs.update(review_id, status="complete", stage="complete",
                  note=(f"No study met every criterion of the protocol: {c['assessed_full_text']} were assessed in full and all excluded, "
                        f"and {c['not_retrieved']} had no legal open full text. Loosening the criterion that excluded most "
                        f"({max(c['excluded_full_text_reasons'] or {'—': 0}, key=(c['excluded_full_text_reasons'] or {'—': 0}).get)}), "
                        "or uploading the paywalled PDFs, would let more studies in."))
        yield "counts", c
        yield "review_complete", {"review_id": review_id, "trial_id": None, "included": 0, "note": rs.get(review_id)["note"]}
        return
    trial_id = rev["trial_id"]
    if not trial_id:
        trial_id = store.create_trial(rev["thread_id"], rev["hypothesis"], rev["subclaims"])
        store.update_trial(trial_id, status="running", strategy_json={"source": f"systematic review {review_id}"})
        rs.update(review_id, trial_id=trial_id)
    t = store.get_trial(trial_id)
    q: asyncio.Queue = asyncio.Queue()
    workers = []
    for r in rs.records(review_id):
        if (_final(r, "ft") or {}).get("decision") == "include" and not r["paper_id"]:
            pid = store.add_paper(trial_id, r["meta"])
            rs.update_record(r["record_id"], paper_id=pid)
            yield "included", {"record_id": r["record_id"], "paper_id": pid, "meta": r["meta"]}
            workers.append(asyncio.create_task(trial_mod._process(t, pid, r["meta"], q)))
    pending = len(workers)
    while pending:
        name, payload = await q.get()
        if name in ("matrix_row", "paper_skipped", "paper_failed"):
            pending -= 1
        yield name, payload
    yield "judging", {"trial_id": trial_id}
    verdict = await trial_mod._verdict(store.get_trial(trial_id), {"ran": False, "fields": []})
    store.update_trial(trial_id, verdict_json=verdict, status="complete")
    rs.update(review_id, status="complete", stage="complete")
    yield "verdict", verdict
    yield "counts", prisma_counts(review_id)
    yield "review_complete", {"review_id": review_id, "trial_id": trial_id, "included": prisma_counts(review_id)["included"]}


async def run(review_id: str, mode: str, protocol_edits: Optional[Dict[str, Any]] = None) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    rev = rs.get(review_id)
    if not rev:
        yield "error", {"error": "No such review."}
        return
    if not rs.claim(review_id):
        yield "error", {"error": f"This review is {rev['status']}; only a planned review you approve can start, and only once."}
        return
    protocol = rev["protocol"]
    if isinstance(protocol_edits, dict):
        elig = protocol_edits.get("eligibility") or {}
        protocol["eligibility"].update({c: str(elig[c]).strip() for c in CRITERIA if c in elig})
        if isinstance(protocol_edits.get("search"), dict):
            protocol["search"].update({k: str(v) for k, v in protocol_edits["search"].items() if k in ("openalex", "europepmc")})
    rs.update(review_id, mode="auto" if mode == "auto" else "copilot", protocol_json=protocol)
    yield "review_start", {"review_id": review_id, "mode": rs.get(review_id)["mode"], "protocol": protocol}
    async for ev in advance(review_id):
        yield ev


async def resume(review_id: str) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    rev = rs.get(review_id)
    if not rev or rev["status"] not in ("awaiting_researcher", "complete", "blocked"):
        yield "error", {"error": "This review is not waiting for you."}
        return
    stage = "ta" if rev["stage"] == "screening_ta" else "ft"
    if rev["status"] == "awaiting_researcher" and queue(review_id, stage):
        yield "paused", {"stage": stage, "queue": queue(review_id, stage)}
        return
    if rev["status"] == "blocked":
        # Clear "unscreened" markers so the Screener tries those records again.
        for r in rs.records(review_id):
            sc = dict(r["screening"])
            changed = False
            for st in ("ta", "ft"):
                if (sc.get(st) or {}).get("decision") == "unscreened":
                    sc.pop(st)
                    changed = True
            if changed:
                rs.update_record(r["record_id"], screening_json=sc)
    rs.update(review_id, status="running", note="")
    async for ev in advance(review_id):
        yield ev


def state(review_id: str) -> Optional[Dict[str, Any]]:
    rev = rs.get(review_id)
    if not rev:
        return None
    return {**rev, "counts": prisma_counts(review_id), "queue_ta": queue(review_id, "ta"), "queue_ft": queue(review_id, "ft"),
            "records": [{"record_id": r["record_id"], "title": r["meta"].get("title"), "year": r["meta"].get("year"), "url": r["meta"].get("url"),
                         "source": r["source"], "dup_of": r["dup_of"], "ta": _final(r, "ta"), "ft": _final(r, "ft"),
                         "ft_access": r["ft_access"], "paper_id": r["paper_id"]} for r in rs.records(review_id)]}
