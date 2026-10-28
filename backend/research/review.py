"""Systematic review (docs/features/05-literature.md tier 3; prompts in 09 § Librarian protocol, § Screener).

A protocol and a budget the researcher approves → identification (OpenAlex, Europe PMC and Semantic Scholar,
paged; every request logged; duplicates counted, not hidden) → title/abstract screening → citation searching
(references of, and papers citing, the records that passed; screened the same way) → full-text retrieval and
screening → included studies become a linked trial (records, appraisals, matrix rows, verdict). Two modes:
  copilot  the run pauses at each screening stage until the researcher has confirmed every decision;
  auto     decisions apply; low-confidence ones (< 0.7) are queued for audit without blocking.

When a search stops is decided by recorded rules (vision §5.7), never silently (sys_reviews.stopping_json):
  source_exhausted        a database returned every match it had;
  budget_reached          the researcher's record budget for a database was used (the total available is kept);
  consecutive_irrelevant  title/abstract screening of keyword results stopped after K irrelevant records in a row
                          (relevance order); the rest are counted as "not screened (stopping rule)";
  citation_saturation     a citation round found no new relevant record;
  citation_rounds_max / citation_budget_reached / citation_off;
  ft_budget               eligible records beyond the full-text budget were not retrieved (and are counted);
  source_error / user_stop.
Reaching these conditions means the documented criteria were met; it never proves nothing else exists.

PRISMA 2020 counts are computed only from stored records and search rows, after every change. Nothing is
decided on the model's behalf: if the Screener cannot be reached, records stay "unscreened" and the run stops.
The run is re-entrant: every stage only processes what still lacks its result, so Stop, a restart, or a raised
budget resumes where it left off.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections import Counter
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx

from backend.agents import sanitize_log_message
from backend.research import analyst, citations, librarian, reader, store, trial as trial_mod
from backend.research import review_store as rs
from backend.research.llm import call_json

logger = logging.getLogger("ThothReview")

IDENT_LIMIT = 25          # kept for importers; identification now pages up to the budget (DEFAULT_BUDGET)
PAGE = 100                # records per OpenAlex / Europe PMC request (OpenAlex caps a page at 100)
TA_BATCH = 4              # records per Screener call at title/abstract stage
TA_WAVE = 3               # Screener calls in flight at once (MODEL_SLOTS caps the whole process at 4)
AUDIT_BELOW = 0.7         # Auto mode: decisions below this confidence are queued for the researcher
FT_TEXT_CHARS = 6000      # focused full text given to the Screener
CRITERIA = ("population", "exposure", "comparison", "outcomes", "designs", "dates", "languages")
SEEDS_PER_ROUND = 10
BACKWARD_PER_SEED = 40
FORWARD_PER_SEED = 20
QUOTA = (("Europe PMC", 0.35), ("Semantic Scholar", 0.15), ("OpenAlex", 1.0))  # OpenAlex takes what is left

# The optimal trade-off (plan §4): identification is free (API calls), screening is cheap (a quarter of a call per
# record), full-text reading is the expensive step (Screener + Reader + Appraiser + Analyst, about a minute each).
DEFAULT_BUDGET = {"keyword_records": 300, "citation_records": 200, "citation_rounds": 2, "stop_after_irrelevant": 50, "full_text": 30}
BUDGET_BOUNDS = {"keyword_records": (50, 1000), "citation_records": (0, 500), "citation_rounds": (0, 3),
                 "stop_after_irrelevant": (0, 200), "full_text": (5, 80)}


def clean_budget(b: Optional[Dict[str, Any]]) -> Dict[str, int]:
    out = dict(DEFAULT_BUDGET)
    for k, (lo, hi) in BUDGET_BOUNDS.items():
        try:
            v = int((b or {}).get(k, out[k]))
        except (TypeError, ValueError):
            continue
        v = max(lo, min(hi, v))
        if k == "stop_after_irrelevant" and 0 < v < 20:
            v = 20
        out[k] = v
    return out


def estimate(budget: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    b = clean_budget(budget)
    ta_calls = math.ceil((b["keyword_records"] + b["citation_records"]) / TA_BATCH)
    ft_calls = b["full_text"] * 4 + 2
    low = round(ta_calls * 0.15 + b["full_text"] * 0.8)
    stop = (f"; screening stops early after {b['stop_after_irrelevant']} irrelevant records in a row"
            if b["stop_after_irrelevant"] else "")
    cites = (f", then up to {b['citation_records']} more by following citations ({b['citation_rounds']} round{'s' if b['citation_rounds'] != 1 else ''})"
             if b["citation_rounds"] and b["citation_records"] else "; citation searching off")
    return {
        "label": "Systematic review (PRISMA 2020)",
        "scope": (f"up to {b['keyword_records']} records from OpenAlex, Europe PMC and Semantic Scholar{cites}{stop}; "
                  f"up to {b['full_text']} full texts read, appraised and weighed"),
        "duration": f"about {low}-{2 * low} minutes on the free tier (stopping rules usually end screening early; plus your screening time in Human-in-the-loop mode)",
        "model_calls": f"up to {ta_calls + ft_calls}",
    }


ESTIMATE = estimate(DEFAULT_BUDGET)

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
- Decide every record you are given, using its record_id exactly.
- Inside evidence strings, quote the record with single quotes ('like this'); never put a double quote inside a JSON string."""


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
        logger.warning("[review] protocol draft failed: %s", sanitize_log_message(str(exc)))
        raw, degraded = {}, True
    protocol = _clean_protocol(raw if isinstance(raw, dict) else {}, q)
    try:
        subclaims = (await analyst.subclaims(hypothesis))["subclaims"]
    except Exception:
        subclaims = []
    subclaims = subclaims or [{"id": 1, "claim": hypothesis, "constructs": [], "relation": "associated_with"}]
    rid = rs.create(thread_id, hypothesis, protocol, subclaims)
    rs.update(rid, budget_json=DEFAULT_BUDGET)
    return {"review_id": rid, "hypothesis": hypothesis, "protocol": protocol, "subclaims": subclaims,
            "budget": DEFAULT_BUDGET, "budget_bounds": BUDGET_BOUNDS, "estimate": ESTIMATE, "degraded": degraded}


# ---------------------------------------------------------------- stopping rules

def _add_stop(review_id: str, rule: str, scope: str, detail: str) -> Optional[Dict[str, Any]]:
    """Record why a search (or part of it) stopped. Idempotent per (rule, scope); never deleted, only superseded."""
    stops = rs.get(review_id)["stopping"]
    if any(s["rule"] == rule and s["scope"] == scope and not s.get("superseded") for s in stops):
        return None
    entry = {"rule": rule, "scope": scope, "detail": detail, "at": time.time()}
    rs.update(review_id, stopping_json=stops + [entry])
    return entry


def _supersede(review_id: str, rules: Tuple[str, ...], scope: Optional[str] = None) -> None:
    stops = rs.get(review_id)["stopping"]
    for s in stops:
        if s["rule"] in rules and not s.get("superseded") and (scope is None or s["scope"] == scope):
            s["superseded"] = True
    rs.update(review_id, stopping_json=stops)


def _active_stops(review_id: str) -> List[Dict[str, Any]]:
    return [s for s in rs.get(review_id)["stopping"] if not s.get("superseded")]


STOPS: set = set()


def request_stop(review_id: str) -> None:
    STOPS.add(review_id)
    rev = rs.get(review_id)
    if rev and rev.get("trial_id"):
        trial_mod.request_stop(rev["trial_id"])


def _stopping_now(review_id: str) -> bool:
    return review_id in STOPS


def _stop_events(review_id: str) -> List[Tuple[str, Dict[str, Any]]]:
    STOPS.discard(review_id)
    rev = rs.get(review_id)
    rs.update(review_id, status="stopped")
    entry = _add_stop(review_id, "user_stop", rev["stage"], f"Stopped by the researcher during {rev['stage'].replace('_', ' ')}.")
    out = [("counts", prisma_counts(review_id))]
    if entry:
        out.append(("stop_rule", entry))
    out.append(("stopped", {"review_id": review_id, "stage": rev["stage"],
                            "message": "Stopped. Everything recorded so far is kept; Continue picks up where it stopped."}))
    return out


# ---------------------------------------------------------------- counts

def _final(rec: Dict[str, Any], stage: str) -> Optional[Dict[str, Any]]:
    return (rec.get("screening") or {}).get(stage)


def _kind(rec: Dict[str, Any]) -> str:
    return (rec.get("origin") or {}).get("kind") or "keyword"


def prisma_counts(review_id: str) -> Dict[str, Any]:
    """PRISMA 2020 flow, computed only from stored records and the search log. `screened` keeps its original
    meaning (records entering screening); `screened_by_screener` excludes those not screened or not yet screened."""
    recs = rs.records(review_id)
    searches = rs.searches(review_id)
    by_source = Counter(r["source"] for r in recs)
    dups = [r for r in recs if r["dup_of"]]
    screened = [r for r in recs if not r["dup_of"]]
    ta = [(r, _final(r, "ta")) for r in screened]
    ta_excluded = [r for r, d in ta if d and d["decision"] == "exclude"]
    unscreened = [r for r, d in ta if not d or d["decision"] == "unscreened"]
    stopped = [r for r, d in ta if d and d["decision"] == "not_screened"]
    sought = [r for r, d in ta if d and d["decision"] in ("include", "maybe")]
    not_retrieved = [r for r in sought if r["ft_access"] in ("abstract_only", "metadata_only")]
    budgeted = [r for r in sought if r["ft_access"] == "budget"]
    assessed = [r for r in sought if r["ft_access"] == "full_text"]
    ft = [(r, _final(r, "ft")) for r in assessed]
    ft_excluded = [(r, d) for r, d in ft if d and d["decision"] == "exclude"]
    ft_unscreened = [r for r, d in ft if not d or d["decision"] == "unscreened"]
    included = [r for r, d in ft if d and d["decision"] == "include"]
    cited = [r for r in recs if _kind(r) in ("backward", "forward")]
    cited_unique = [r for r in cited if not r["dup_of"]]
    return {
        "identified": len(recs), "by_source": dict(by_source), "duplicates_removed": len(dups),
        "identified_databases": len(recs) - len(cited), "identified_citations": len(cited),
        "removed_before_screening": {"duplicates": len(dups),
                                     "automated_offtopic": sum(int(s.get("removed_offtopic") or 0) for s in searches),
                                     "no_title": sum(max(0, int(s.get("returned") or 0) - int(s.get("new_unique") or 0) - int(s.get("duplicates") or 0))
                                                     for s in searches if not s.get("error"))},
        "screened": len(screened), "excluded_title_abstract": len(ta_excluded),
        "excluded_title_abstract_reasons": dict(Counter(_final(r, "ta").get("reason") or "unspecified" for r in ta_excluded)),
        "unscreened": len(unscreened), "not_screened_stopped": len(stopped),
        "screened_by_screener": len(screened) - len(unscreened) - len(stopped),
        "sought_for_retrieval": len(sought), "not_retrieved": len(not_retrieved), "not_retrieved_budget": len(budgeted),
        "awaiting_retrieval": len([r for r in sought if not r["ft_access"]]),
        "assessed_full_text": len(assessed),
        "excluded_full_text": len(ft_excluded),
        "excluded_full_text_reasons": dict(Counter(d.get("reason") or "unspecified" for _, d in ft_excluded)),
        "full_text_unscreened": len(ft_unscreened),
        "included": len(included),
        "citation": {"rounds": max([(r.get("origin") or {}).get("round", 0) for r in cited] or [0]),
                     "seeds": sum(1 for r in recs if (r.get("origin") or {}).get("seeded_round")),
                     "found": len(cited), "new_unique": len(cited_unique),
                     "included": sum(1 for r in included if _kind(r) in ("backward", "forward"))},
        "searches": len(searches),
    }


def limitations(review_id: str) -> List[str]:
    """Plain sentences for the researcher, the Judge and the proposal: what this search did not cover, and why."""
    out = [s["detail"] for s in _active_stops(review_id) if s["rule"] != "user_stop"]
    stopped_sources = {s["scope"] for s in _active_stops(review_id) if s["rule"] == "source_error"}
    for s in rs.searches(review_id):
        if s.get("error") and s["source"] not in stopped_sources:
            out.append(f"{s['source']} ({s['kind']}) failed once: {s['error']}")
    c = prisma_counts(review_id)
    if c["not_retrieved"]:
        out.append(f"{c['not_retrieved']} eligible record(s) had no legal open full text and could not be assessed in full.")
    p = (rs.get(review_id) or {}).get("protocol") or {}
    lang = ((p.get("eligibility") or {}).get("languages") or "").strip()
    if lang:
        out.append(f"Language restriction from the protocol: {lang}")
    out.append("OpenAlex was searched in its curated core corpus (journal articles and reviews); its opt-in expansion of "
               "datasets and repository records was not searched.")
    out.append("Reaching these stopping conditions means the documented search criteria were met; it does not prove that "
               "no other relevant literature exists.")
    return list(dict.fromkeys(out))


def coverage(review_id: str) -> Dict[str, Any]:
    c = prisma_counts(review_id)
    return {"kind": "systematic_review", "review_id": review_id, "identified": c["identified"],
            "identified_databases": c["identified_databases"], "identified_citations": c["identified_citations"],
            "screened": c["screened_by_screener"], "included": c["included"],
            "stopped_because": [s["detail"] for s in _active_stops(review_id)], "limitations": limitations(review_id)}


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


RETRY_NOTE = ("\n<format_note>Your previous answer for this record was not valid JSON (a double quote inside an evidence "
              "string). Use single quotes inside every string.</format_note>")


async def _screen(protocol: Dict[str, Any], items: List[Tuple[Dict[str, Any], str]], stage: str, mode: str,
                  retry: bool = False) -> Dict[str, Dict[str, Any]]:
    """items: (record, text). Returns record_id → decision. Records the Screener didn't decide are absent. A retry
    carries a format note: the usual cause of an empty answer is a quoted phrase that broke the JSON (29 Oct 2026)."""
    human = (f"<protocol>{json.dumps(protocol['eligibility'])}</protocol>\n<stage>{'title_abstract' if stage == 'ta' else 'full_text'}</stage>\n"
             + "\n".join(f"<untrusted record_id=\"{r['record_id']}\">\n{text}\n</untrusted>" for r, text in items)
             + (RETRY_NOTE if retry else ""))
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
        if r["dup_of"] or not d or d.get("by") in ("user", "stopping_rule"):
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


# ---------------------------------------------------------------- identification (paged, logged, re-entrant)

def _deduper(review_id: str) -> librarian.Deduper:
    d = librarian.Deduper()
    for r in rs.records(review_id):
        if not r["dup_of"]:
            d.add(r["meta"], r["record_id"])
    return d


def _store_results(review_id: str, found: List[Dict[str, Any]], dedup: librarian.Deduper, origin: Dict[str, Any],
                   rank_base: int, rank_step: int = 1) -> Tuple[int, int, int]:
    """Records every result (duplicates included, flagged dup_of). Returns (new_unique, duplicates, no_title)."""
    new, dups, no_title = 0, 0, 0
    for i, meta in enumerate(found):
        if not meta.get("title"):
            no_title += 1
            continue
        ref = dedup.match(meta)
        rid = rs.add_record(review_id, meta, meta.get("found_via", ""), ref, ids=librarian.ids_of(meta), origin=origin,
                            rank=rank_base + i * rank_step)
        if ref is None:
            dedup.add(meta, rid)
            new += 1
        else:
            dups += 1
    return new, dups, no_title


async def _identify(rev: Dict[str, Any], budget: Dict[str, int]) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    review_id = rev["review_id"]
    p = rev["protocol"]["search"]
    dedup = _deduper(review_id)
    total_budget = budget["keyword_records"]
    used = Counter((r.get("origin") or {}).get("source") for r in rs.records(review_id) if _kind(r) == "keyword")
    async with httpx.AsyncClient(timeout=20, headers=librarian.UA, follow_redirects=True) as client:
        for slot, (source, share) in enumerate(QUOTA):
            remaining_overall = total_budget - sum(used.values())
            quota = remaining_overall if source == "OpenAlex" else min(remaining_overall, int(total_budget * share) - used[source])
            rows = [s for s in rs.searches(review_id) if s["kind"] == "keyword" and s["source"] == source]
            last = rows[-1] if rows else None
            if last and not last.get("next_cursor") and not last.get("error"):
                continue  # this database is finished (exhausted or budget), recorded before
            if quota <= 0:
                entry = _add_stop(review_id, "budget_reached", source, f"{source}: no record budget was left for it.")
                if entry:
                    yield "stop_rule", entry
                continue
            retrying = bool(last and last.get("error"))
            page = (last["page"] + (0 if retrying else 1)) if last else 1
            cursor = (last.get("next_cursor") if last else None) or "*"
            query = (last or {}).get("query") or (p["openalex"] if source in ("OpenAlex", "Semantic Scholar") else p["europepmc"])
            while quota > 0:
                if _stopping_now(review_id):
                    return
                per = min(PAGE, quota)
                info: Dict[str, Any] = {}
                dropped: List[str] = []
                if source == "OpenAlex":
                    found = await librarian.search_openalex(client, query, per, cursor=cursor, page_info=info)
                elif source == "Europe PMC":
                    found = await librarian.search_europepmc(client, query, per, dropped, cursor=cursor, page_info=info)
                    if page == 1 and len(found) < 3 and not info.get("error"):
                        # A Boolean query that ANDs too many blocks returns almost nothing; relax it (logged as its own search).
                        query = librarian.keywords(p["openalex"], 8)
                        info, dropped, cursor = {}, [], "*"
                        found = await librarian.search_europepmc(client, query, per, dropped, cursor=cursor, page_info=info)
                else:
                    found, info = await librarian.search_s2(query, per, None if cursor == "*" else cursor)
                origin = {"kind": "keyword", "source": source, "round": 0, "page": page}
                new, dups, no_title = _store_results(review_id, found, dedup, origin, rank_base=(page - 1) * 1000 + slot, rank_step=3)
                n = new + dups
                used[source] += n
                quota -= n
                nxt = info.get("next_cursor")
                rs.add_search(review_id, round=0, kind="keyword", source=source, query=query, page=page, requested=per,
                              returned=len(found) + no_title, new_unique=new, duplicates=dups, removed_offtopic=len(dropped),
                              total_available=info.get("total"), next_cursor=(cursor if info.get("error") else nxt), error=info.get("error"),
                              cost_usd=info.get("cost_usd"))
                if retrying and not info.get("error"):
                    _supersede(review_id, ("source_error",), scope=source)
                    retrying = False
                yield "search_page", {"source": source, "page": page, "returned": len(found), "new_unique": new,
                                      "total_available": info.get("total"), "error": info.get("error")}
                if info.get("error"):
                    entry = _add_stop(review_id, "source_error", source, f"{source}: the search failed ({info['error'][:120]}); "
                                      f"{used[source]} record(s) were retrieved from it before that.")
                    if entry:
                        yield "stop_rule", entry
                    break  # Continue retries this page
                total = info.get("total")
                more = bool(nxt) or (total is not None and used[source] < int(total))
                if (not nxt or not found) and not (quota <= 0 and more):
                    entry = _add_stop(review_id, "source_exhausted", source,
                                      f"{source}: all {total if total is not None else used[source]} match(es) for the query were retrieved.")
                    if entry:
                        yield "stop_rule", entry
                    break
                if quota <= 0:
                    rs.add_search(review_id, round=0, kind="keyword", source=source, query=query, page=page, requested=0,
                                  returned=0, total_available=total, next_cursor=None, error=None)
                    entry = _add_stop(review_id, "budget_reached", source,
                                      f"{source}: the first {used[source]} of {total if total is not None else 'an unknown number of'} "
                                      "matches by relevance were retrieved (record budget).")
                    if entry:
                        yield "stop_rule", entry
                    break
                cursor, page = nxt, page + 1
    yield "counts", prisma_counts(review_id)


# ---------------------------------------------------------------- title/abstract screening with rule S4

def _pending_ta(review_id: str, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    recs = [r for r in rs.records(review_id) if not r["dup_of"] and not _final(r, "ta")]
    if kind == "keyword":
        recs = [r for r in recs if _kind(r) == "keyword"]
    elif kind == "citation":
        recs = [r for r in recs if _kind(r) != "keyword"]
    return sorted(recs, key=lambda r: ((r.get("origin") or {}).get("round", 0), r.get("rank") if r.get("rank") is not None else 10 ** 9))


def _s4_fires(review_id: str, k: int) -> Tuple[bool, int, int]:
    """Trailing run of Screener excludes among screened keyword records in relevance order."""
    kw = sorted([r for r in rs.records(review_id) if not r["dup_of"] and _kind(r) == "keyword"],
                key=lambda r: r.get("rank") if r.get("rank") is not None else 10 ** 9)
    screened = [r for r in kw if _final(r, "ta") and _final(r, "ta")["decision"] not in ("unscreened", "not_screened")]
    run = 0
    for r in reversed(screened):
        d = _final(r, "ta")
        if (d.get("decision") if d.get("by") == "user" else d.get("screener_decision") or d.get("decision")) == "exclude":
            run += 1
        else:
            break
    return (k > 0 and run >= k and len(screened) >= 2 * k), len(screened), len(kw)


def _recheck_s4(review_id: str) -> bool:
    """After the researcher overrides a decision inside the trailing run, the rule no longer holds: the records it
    left unscreened go back to screening and the entry is marked superseded (kept in the history)."""
    stops = [s for s in _active_stops(review_id) if s["rule"] == "consecutive_irrelevant"]
    if not stops:
        return False
    k = clean_budget(rs.get(review_id)["budget"])["stop_after_irrelevant"]
    fires, _, _ = _s4_fires(review_id, k)
    if fires:
        return False
    for r in rs.records(review_id):
        d = _final(r, "ta")
        if d and d.get("by") == "stopping_rule":
            sc = dict(r["screening"])
            sc.pop("ta")
            rs.update_record(r["record_id"], screening_json=sc)
    _supersede(review_id, ("consecutive_irrelevant",))
    return True


async def _screen_ta(review_id: str, rev: Dict[str, Any], mode: str, budget: Dict[str, int], kind: str) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    """Screens pending records of one kind (keyword or citation), in waves of TA_WAVE batches. Yields "blocked"
    (and returns) if the Screener fails; applies S4 to keyword records after every wave."""
    k = budget["stop_after_irrelevant"] if kind == "keyword" else 0
    todo = _pending_ta(review_id, kind)
    total = len(todo)
    done = 0
    while todo:
        if _stopping_now(review_id):
            return
        wave = [todo[i:i + TA_BATCH] for i in range(0, min(len(todo), TA_BATCH * TA_WAVE), TA_BATCH)]
        todo = todo[TA_BATCH * TA_WAVE:]

        async def one(batch):
            try:
                got = await _screen(rev["protocol"], [(r, _ta_text(r)) for r in batch], "ta", mode)
            except Exception as exc:
                logger.warning("[review] screener failed: %s", sanitize_log_message(str(exc)))
                got = {}
            for r in [r for r in batch if r["record_id"] not in got]:
                # A batch answer can be cut short or come back empty (seen 29 Oct 2026, one batch of 148); try the
                # records it missed one at a time before giving up.
                try:
                    got.update(await _screen(rev["protocol"], [(r, _ta_text(r))], "ta", mode, retry=True))
                except Exception:
                    pass
            return batch, got

        failed = False
        for batch, got in await asyncio.gather(*[one(b) for b in wave]):
            for r in batch:
                if r["record_id"] in got:
                    rs.update_record(r["record_id"], screening_json={**r["screening"], "ta": got[r["record_id"]]})
                else:
                    rs.update_record(r["record_id"], screening_json={**r["screening"], "ta": {"decision": "unscreened", "by": "nobody"}})
                    failed = True
            done += len(batch)
        if failed:
            rs.update(review_id, status="blocked", note="The Screener couldn't be reached or returned no decision for some records; they stay unscreened. Nothing was decided on its behalf.")
            yield "counts", prisma_counts(review_id)
            yield "blocked", {"stage": "ta", "reason": rs.get(review_id)["note"]}
            return
        yield "screening_progress", {"stage": "ta", "done": done, "total": total}
        yield "counts", prisma_counts(review_id)
        if k:
            fires, n_screened, n_kw = _s4_fires(review_id, k)
            if fires and todo:
                for r in todo:
                    rs.update_record(r["record_id"], screening_json={**r["screening"], "ta": {
                        "decision": "not_screened", "by": "stopping_rule", "needs_review": False,
                        "reason": f"{k} consecutive records ranked above it were irrelevant"}})
                entry = _add_stop(review_id, "consecutive_irrelevant", "title/abstract",
                                  f"Title/abstract screening of the database results stopped after {k} consecutive irrelevant records "
                                  f"(screened {n_screened} of {n_kw}; the remaining {len(todo)} are counted as not screened).")
                if entry:
                    yield "stop_rule", entry
                yield "counts", prisma_counts(review_id)
                return


# ---------------------------------------------------------------- citation rounds

def _seed_candidates(review_id: str) -> List[Dict[str, Any]]:
    recs = [r for r in rs.records(review_id) if not r["dup_of"] and (_final(r, "ta") or {}).get("decision") in ("include", "maybe")
            and not (r.get("origin") or {}).get("seeded_round")]
    return sorted(recs, key=lambda r: ((_final(r, "ta") or {}).get("decision") != "include", -float((_final(r, "ta") or {}).get("confidence") or 0),
                                       r.get("rank") if r.get("rank") is not None else 10 ** 9))[:SEEDS_PER_ROUND]


def _round_seeds(review_id: str, rnd: int) -> List[Dict[str, Any]]:
    return [r for r in rs.records(review_id) if (r.get("origin") or {}).get("seeded_round") == rnd]


def _citations_done(review_id: str) -> bool:
    return any(s["rule"] in ("citation_saturation", "citation_rounds_max", "citation_budget_reached", "citation_off")
               for s in _active_stops(review_id))


def _current_round(review_id: str) -> int:
    return max([(r.get("origin") or {}).get("seeded_round") or 0 for r in rs.records(review_id)] or [0])


async def _chase(review_id: str, rnd: int, budget: Dict[str, int], query: str) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    """Look up each seed of this round that hasn't been looked up yet (re-entrant), recording every call."""
    dedup = _deduper(review_id)
    seeds = _round_seeds(review_id, rnd)
    looked = {s["seed_record_id"] for s in rs.searches(review_id) if s["kind"] in ("backward", "forward") and s["round"] == rnd}
    found_total = new_total = 0
    async with httpx.AsyncClient(timeout=20, headers=librarian.UA, follow_redirects=True) as client:
        for seed in seeds:
            if seed["record_id"] in looked:
                continue
            for kind, fn, per in (("backward", citations.backward, BACKWARD_PER_SEED), ("forward", citations.forward, FORWARD_PER_SEED)):
                if _stopping_now(review_id):
                    return
                used = sum(1 for r in rs.records(review_id) if _kind(r) != "keyword")
                remaining = budget["citation_records"] - used
                if remaining <= 0:
                    entry = _add_stop(review_id, "citation_budget_reached", "citations",
                                      f"Citation searching stopped at its budget of {budget['citation_records']} records.")
                    if entry:
                        yield "stop_rule", entry
                    return
                papers, info = await fn(client, seed["meta"], min(per, remaining), query=query)
                origin = {"kind": kind, "seed_record_id": seed["record_id"], "round": rnd, "provider": info.get("provider")}
                new, dups, _nt = _store_results(review_id, papers, dedup, origin, rank_base=rnd * 100000 + len(rs.records(review_id)))
                found_total += new + dups
                new_total += new
                rs.add_search(review_id, round=rnd, kind=kind, source=info.get("provider") or "OpenAlex", query=query,
                              seed_record_id=seed["record_id"], page=1, requested=info.get("requested"), returned=len(papers),
                              new_unique=new, duplicates=dups, removed_offtopic=info.get("removed_offtopic") or 0,
                              total_available=info.get("total_available"), next_cursor=None, error=info.get("error"))
    yield "citation_round", {"round": rnd, "seeds": len(seeds), "found": found_total, "new_unique": new_total}


async def _citation_rounds(review_id: str, rev: Dict[str, Any], mode: str, budget: Dict[str, int]) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    """Each round: look up the seeds → screen what was found → judge the round (saturation, rounds, budget) →
    choose the next seeds. Re-entrant at every step. Yields ("_halt", why) when the run must return."""
    if budget["citation_rounds"] == 0 or budget["citation_records"] == 0:
        entry = _add_stop(review_id, "citation_off", "citations", "Citation searching was turned off for this review.")
        if entry:
            yield "stop_rule", entry
        return
    query = rev["protocol"]["search"]["openalex"]
    while not _citations_done(review_id):
        rnd = _current_round(review_id)
        if rnd:
            looked = {s["seed_record_id"] for s in rs.searches(review_id) if s["kind"] in ("backward", "forward") and s["round"] == rnd}
            if not all(s["record_id"] in looked for s in _round_seeds(review_id, rnd)):
                rs.update(review_id, stage="citation_chasing")
                async for ev in _chase(review_id, rnd, budget, query):
                    yield ev
                if _stopping_now(review_id):
                    yield "_halt", {"why": "stopped"}
                    return
            async for ev in _screen_ta(review_id, rev, mode, budget, "citation"):
                yield ev
                if ev[0] == "blocked":
                    yield "_halt", {"why": "blocked"}
                    return
            if _stopping_now(review_id):
                yield "_halt", {"why": "stopped"}
                return
            if mode == "copilot" and queue(review_id, "ta"):
                rs.update(review_id, status="awaiting_researcher", stage="citation_chasing")
                yield "paused", {"stage": "ta", "queue": queue(review_id, "ta")}
                yield "_halt", {"why": "paused"}
                return
            if _citations_done(review_id):
                return
            new = [r for r in rs.records(review_id) if (r.get("origin") or {}).get("round") == rnd and _kind(r) != "keyword" and not r["dup_of"]]
            relevant = [r for r in new if (_final(r, "ta") or {}).get("decision") in ("include", "maybe")]
            if not relevant:
                entry = _add_stop(review_id, "citation_saturation", f"round {rnd}",
                                  f"Citation round {rnd} found no new relevant record, so citation searching stopped (saturation).")
                if entry:
                    yield "stop_rule", entry
                return
            if rnd >= budget["citation_rounds"]:
                entry = _add_stop(review_id, "citation_rounds_max", "citations",
                                  f"Citation searching stopped after the {rnd} round(s) the budget allows; the last round still found "
                                  f"{len(relevant)} relevant record(s).")
                if entry:
                    yield "stop_rule", entry
                return
        cands = _seed_candidates(review_id)
        if not cands:
            entry = _add_stop(review_id, "citation_saturation", f"round {rnd + 1}", "No new relevant record was left to follow citations from.")
            if entry:
                yield "stop_rule", entry
            return
        for r in cands:
            rs.update_record(r["record_id"], origin_json={**(r.get("origin") or {}), "seeded_round": rnd + 1})


# ---------------------------------------------------------------- the run

def _ft_priority(r: Dict[str, Any]) -> Tuple:
    d = _final(r, "ta") or {}
    return (d.get("decision") != "include", -float(d.get("confidence") or 0), r.get("rank") if r.get("rank") is not None else 10 ** 9)


async def advance(review_id: str) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    """Run from wherever the review is until it pauses for the researcher, is blocked, stops, or completes.
    Every step only processes records that still lack its result, so it is safe to call again."""
    rev = rs.get(review_id)
    mode = rev["mode"]
    budget = clean_budget(rev.get("budget"))
    if rev["stage"] in ("planned", "identifying"):
        rs.update(review_id, stage="identifying")
        async for ev in _identify(rs.get(review_id), budget):
            yield ev
        if _stopping_now(review_id):
            for ev in _stop_events(review_id):
                yield ev
            return
        rs.update(review_id, stage="screening_ta")

    # Title/abstract screening of the database results (rule S4 applies), then the researcher's turn.
    if rs.get(review_id)["stage"] == "screening_ta":
        async for ev in _screen_ta(review_id, rev, mode, budget, "keyword"):
            yield ev
            if ev[0] == "blocked":
                return
        if _stopping_now(review_id):
            for ev in _stop_events(review_id):
                yield ev
            return
        if mode == "copilot" and queue(review_id, "ta"):
            rs.update(review_id, status="awaiting_researcher", stage="screening_ta")
            yield "paused", {"stage": "ta", "queue": queue(review_id, "ta")}
            return

    # Citation searching from what passed, in rounds, until a recorded rule stops it.
    if rs.get(review_id)["stage"] in ("screening_ta", "citation_chasing"):
        async for ev in _citation_rounds(review_id, rs.get(review_id), mode, budget):
            if ev[0] == "_halt":
                if ev[1]["why"] == "stopped":
                    for e in _stop_events(review_id):
                        yield e
                return
            yield ev
        yield "counts", prisma_counts(review_id)

    # Full-text retrieval, highest priority first, up to the full-text budget.
    rs.update(review_id, status="running", stage="retrieving")
    texts: Dict[str, str] = {}
    sought = sorted([r for r in rs.records(review_id) if not r["dup_of"] and (_final(r, "ta") or {}).get("decision") in ("include", "maybe")],
                    key=_ft_priority)
    slots = budget["full_text"] - sum(1 for r in sought if r["ft_access"] not in (None, "budget"))
    over = 0
    for r in sought:
        if r["ft_access"]:
            continue
        if _stopping_now(review_id):
            for ev in _stop_events(review_id):
                yield ev
            return
        if slots <= 0:
            rs.update_record(r["record_id"], ft_access="budget")
            over += 1
            continue
        text, access, _src = await librarian.full_text(r["meta"])
        rs.update_record(r["record_id"], ft_access=access)
        slots -= 1
        if access == "full_text":
            texts[r["record_id"]] = text
        yield "retrieved", {"record_id": r["record_id"], "access": access}
    n_budget = sum(1 for r in rs.records(review_id) if r["ft_access"] == "budget")
    if n_budget:
        entry = _add_stop(review_id, "ft_budget", "retrieval",
                          f"{n_budget} eligible record(s) were not retrieved: the full-text budget is {budget['full_text']} "
                          "(raise it to read them).")
        if entry:
            yield "stop_rule", entry
    yield "counts", prisma_counts(review_id)

    # Full-text screening, one record per call.
    rs.update(review_id, stage="screening_ft")
    for r in [x for x in rs.records(review_id) if x["ft_access"] == "full_text" and not _final(x, "ft")
              and (_final(x, "ta") or {}).get("decision") in ("include", "maybe")]:
        if _stopping_now(review_id):
            for ev in _stop_events(review_id):
                yield ev
            return
        text = texts.get(r["record_id"])
        if text is None:
            text, _a, _s = await librarian.full_text(r["meta"])
        got: Dict[str, Dict[str, Any]] = {}
        for _attempt in range(2):  # one retry: an empty answer is usually transient (seen 29 Oct 2026)
            try:
                got = await _screen(rev["protocol"], [(r, reader.focus(text, FT_TEXT_CHARS))], "ft", mode, retry=bool(_attempt))
            except Exception:
                got = {}
            if r["record_id"] in got:
                break
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

    async for ev in _synthesis(review_id):
        yield ev


async def _synthesis(review_id: str) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    """Included studies → a linked trial: read, appraised, analysed, weighed. A completed trial is never changed:
    if more studies are included later (a raised budget), a new trial is made and the earlier one is kept."""
    rs.update(review_id, status="running", stage="synthesis")
    rev = rs.get(review_id)
    c = prisma_counts(review_id)
    if c["included"] == 0 and not rev["trial_id"]:
        # A strict protocol can include nothing. Say so plainly; don't create an empty trial.
        unread = (f" {c['not_retrieved_budget']} eligible record(s) were not read at all because of the full-text budget; "
                  "raising it would assess them." if c["not_retrieved_budget"] else "")
        rs.update(review_id, status="complete", stage="complete",
                  note=(f"No study met every criterion of the protocol so far: {c['assessed_full_text']} were assessed in full and all excluded, "
                        f"and {c['not_retrieved']} had no legal open full text.{unread} Loosening the criterion that excluded most "
                        f"({max(c['excluded_full_text_reasons'] or {'—': 0}, key=(c['excluded_full_text_reasons'] or {'—': 0}).get)}), "
                        "or uploading the paywalled PDFs, would let more studies in."))
        yield "counts", c
        yield "review_complete", {"review_id": review_id, "trial_id": None, "included": 0, "note": rs.get(review_id)["note"]}
        return
    from backend.conversation import projects
    included = [r for r in rs.records(review_id) if (_final(r, "ft") or {}).get("decision") == "include"]
    trial_id = rev["trial_id"]
    old = store.get_trial(trial_id) if trial_id else None
    note = rev.get("note") or ""
    if old and old["status"] == "complete" and any(not r["paper_id"] for r in included):
        note = (note + " " if note else "") + f"An earlier synthesis (trial {trial_id}) is kept; this one adds the studies included since."
        trial_id = None
    strategy = {"source": f"systematic review {review_id}", "review_id": review_id, "coverage": coverage(review_id)}
    if not trial_id:
        trial_id = store.create_trial(rev["thread_id"], rev["hypothesis"], rev["subclaims"],
                                      hypothesis_version=projects.version_of(rev["thread_id"], rev["hypothesis"]))
        store.update_trial(trial_id, status="running", strategy_json=strategy)
        rs.update(review_id, trial_id=trial_id, note=note)
    else:
        store.update_trial(trial_id, status="running", strategy_json=strategy)
    t = store.get_trial(trial_id)
    have = {p["paper_id"] for p in t["papers"]}
    q: asyncio.Queue = asyncio.Queue()
    workers = []
    status = {p["paper_id"]: p["status"] for p in t["papers"]}
    for r in included:
        if r["paper_id"] in have:
            if status.get(r["paper_id"]) == "not_run":  # stopped mid-synthesis before: run it now
                workers.append(asyncio.create_task(trial_mod._process(t, r["paper_id"], r["meta"], q)))
            continue
        prev = store.get_paper(r["paper_id"]) if r["paper_id"] else None
        pid = store.add_paper(trial_id, r["meta"])
        rs.update_record(r["record_id"], paper_id=pid)
        yield "included", {"record_id": r["record_id"], "paper_id": pid, "meta": r["meta"]}
        if prev and prev["status"] == "done":
            # Already read, appraised and analysed for this hypothesis in the earlier synthesis: reuse it.
            store.update_paper(pid, access=prev["access"], text_source=prev["text_source"], record_json=prev["record"], row_json=prev["row"],
                               weight=prev["weight"], appraisal_json=prev.get("appraisal") or {}, status="done")
            yield "matrix_row", {"paper_id": pid, "row": prev["row"], "weight": prev["weight"]}
            continue
        workers.append(asyncio.create_task(trial_mod._process(t, pid, r["meta"], q)))
    pending = len(workers)
    while pending:
        if _stopping_now(review_id):
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            for p in store.list_papers(trial_id):
                if p["status"] not in trial_mod.FINAL:
                    store.update_paper(p["paper_id"], status="not_run")
            store.update_trial(trial_id, status="stopped")
            trial_mod.STOPS.discard(trial_id)
            for ev in _stop_events(review_id):
                yield ev
            return
        try:
            name, payload = await asyncio.wait_for(q.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue
        if name in ("matrix_row", "paper_skipped", "paper_failed"):
            pending -= 1
        yield name, payload
    yield "judging", {"trial_id": trial_id}
    # Originality needs prior work beyond the included studies: adjacent fields, and the citation records that
    # passed title/abstract screening but are not witnesses (abstract level only).
    try:
        strat = await librarian.strategy(rev["hypothesis"])
        adjacent = await librarian.adjacent_search(strat)
    except Exception as exc:
        logger.warning("[review] adjacent search failed: %s", sanitize_log_message(str(exc)))
        adjacent = {"ran": False, "fields": []}
    in_trial = {r["record_id"] for r in included}
    neighbours = [r for r in rs.records(review_id) if _kind(r) != "keyword" and not r["dup_of"] and r["record_id"] not in in_trial
                  and (_final(r, "ta") or {}).get("decision") in ("include", "maybe")]
    adjacent["citation"] = {"ran": any(s["kind"] in ("backward", "forward") and not s.get("error") for s in rs.searches(review_id)),
                            "reason": "" if neighbours or _citations_done(review_id) else "Citation searching was turned off or found nothing.",
                            "source": "systematic review",
                            "papers": [{"id": f"C{i}", "title": r["meta"].get("title"), "year": r["meta"].get("year"),
                                        "relation": f"{(r.get('origin') or {}).get('kind')} citation of a screened record",
                                        "abstract": (r["meta"].get("abstract") or "")[:500], "doi": r["meta"].get("doi"), "url": r["meta"].get("url")}
                                       for i, r in enumerate(neighbours[:15], 1)]}
    store.update_trial(trial_id, adjacent_json=adjacent)
    verdict = await trial_mod._verdict(store.get_trial(trial_id), adjacent)
    store.update_trial(trial_id, verdict_json=verdict, status="complete")
    rs.update(review_id, status="complete", stage="complete")
    yield "verdict", verdict
    yield "counts", prisma_counts(review_id)
    yield "review_complete", {"review_id": review_id, "trial_id": trial_id, "included": prisma_counts(review_id)["included"]}


async def run(review_id: str, mode: str, protocol_edits: Optional[Dict[str, Any]] = None,
              budget: Optional[Dict[str, Any]] = None) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    rev = rs.get(review_id)
    if not rev:
        yield "error", {"error": "No such review."}
        return
    if not rs.claim(review_id):
        yield "error", {"error": f"This review is {rev['status']}; only a planned review you approve can start, and only once."}
        return
    STOPS.discard(review_id)
    protocol = rev["protocol"]
    if isinstance(protocol_edits, dict):
        elig = protocol_edits.get("eligibility") or {}
        protocol["eligibility"].update({c: str(elig[c]).strip() for c in CRITERIA if c in elig})
        if isinstance(protocol_edits.get("search"), dict):
            protocol["search"].update({k: str(v) for k, v in protocol_edits["search"].items() if k in ("openalex", "europepmc")})
    b = clean_budget(budget if isinstance(budget, dict) else rev.get("budget"))
    rs.update(review_id, mode="auto" if mode == "auto" else "copilot", protocol_json=protocol, budget_json=b)
    yield "review_start", {"review_id": review_id, "mode": rs.get(review_id)["mode"], "protocol": protocol, "budget": b}
    try:
        async for ev in advance(review_id):
            yield ev
    except asyncio.CancelledError:
        # The page was closed mid-run: the same as Stop (everything recorded is kept; Continue resumes).
        rs.update(review_id, status="stopped")
        STOPS.discard(review_id)
        raise


async def resume(review_id: str) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    rev = rs.get(review_id)
    if not rev or rev["status"] not in ("awaiting_researcher", "complete", "blocked", "stopped"):
        yield "error", {"error": "This review is not waiting for you."}
        return
    stage = "ft" if rev["stage"] == "screening_ft" else "ta"
    if rev["status"] == "awaiting_researcher" and queue(review_id, stage):
        yield "paused", {"stage": stage, "queue": queue(review_id, stage)}
        return
    if _recheck_s4(review_id):
        rs.update(review_id, stage="screening_ta")
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
    if rev["status"] == "stopped":
        _supersede(review_id, ("user_stop",))
    STOPS.discard(review_id)
    rs.update(review_id, status="running", note=rev.get("note") if rev["status"] == "complete" else "")
    try:
        async for ev in advance(review_id):
            yield ev
    except asyncio.CancelledError:
        rs.update(review_id, status="stopped")
        raise


def raise_budget(review_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
    """The researcher gives the review more room (full texts, citation records or rounds). Records left out by the
    old budget become eligible again; the stopping entries that budget caused are superseded, not deleted."""
    rev = rs.get(review_id)
    if not rev:
        raise KeyError(review_id)
    if rev["status"] not in ("awaiting_researcher", "complete", "stopped", "blocked"):
        raise ValueError(f"This review is {rev['status']}; the budget can change only while it is paused, stopped or done.")
    old = clean_budget(rev.get("budget"))
    new = clean_budget({**old, **{k: v for k, v in (changes or {}).items() if k in ("full_text", "citation_records", "citation_rounds")}})
    rs.update(review_id, budget_json=new)
    if new["full_text"] > old["full_text"]:
        for r in rs.records(review_id):
            if r["ft_access"] == "budget":
                rs.update_record(r["record_id"], ft_access=None)
        _supersede(review_id, ("ft_budget",))
    if new["citation_records"] > old["citation_records"] or new["citation_rounds"] > old["citation_rounds"]:
        _supersede(review_id, ("citation_budget_reached", "citation_rounds_max", "citation_off"))
    if rev["status"] == "complete" and rev["stage"] == "complete":
        rs.update(review_id, stage="citation_chasing" if new["citation_rounds"] > old["citation_rounds"] else "retrieving")
    return {"budget": new, "estimate": estimate(new)}


def state(review_id: str) -> Optional[Dict[str, Any]]:
    rev = rs.get(review_id)
    if not rev:
        return None
    # `records` stays for compatibility; the panel pages through /records instead.
    return {**rev, "budget": clean_budget(rev.get("budget")), "estimate": estimate(rev.get("budget")),
            "limitations": limitations(review_id),
            "counts": prisma_counts(review_id), "queue_ta": queue(review_id, "ta"), "queue_ft": queue(review_id, "ft"),
            "records": [{"record_id": r["record_id"], "title": r["meta"].get("title"), "year": r["meta"].get("year"), "url": r["meta"].get("url"),
                         "source": r["source"], "dup_of": r["dup_of"], "ta": _final(r, "ta"), "ft": _final(r, "ft"),
                         "ft_access": r["ft_access"], "paper_id": r["paper_id"]} for r in rs.records(review_id)]}


FILTERS = {
    "all": lambda r: True,
    "included": lambda r: (_final(r, "ft") or {}).get("decision") == "include",
    "excluded_ta": lambda r: (_final(r, "ta") or {}).get("decision") == "exclude",
    "excluded_ft": lambda r: (_final(r, "ft") or {}).get("decision") == "exclude",
    "not_screened": lambda r: (_final(r, "ta") or {}).get("decision") == "not_screened",
    "duplicates": lambda r: bool(r["dup_of"]),
    "citation": lambda r: _kind(r) != "keyword",
}


def records_page(review_id: str, offset: int = 0, limit: int = 50, flt: str = "all") -> Dict[str, Any]:
    keep = FILTERS.get(flt, FILTERS["all"])
    recs = [r for r in rs.records(review_id) if keep(r)]
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))
    return {"total": len(recs), "offset": offset, "limit": limit, "filter": flt if flt in FILTERS else "all",
            "records": [{"record_id": r["record_id"], "meta": {k: r["meta"].get(k) for k in ("title", "year", "venue", "url", "doi")},
                         "source": r["source"], "origin": r.get("origin"), "dup_of": r["dup_of"], "screening": r["screening"],
                         "ft_access": r["ft_access"]} for r in recs[offset:offset + limit]]}
