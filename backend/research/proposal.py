"""The research proposal (docs/features/08-writing.md).

outline (Writer) → the researcher edits and approves → each section: Writer → Verifier → (all written) Reviewer,
FATAL → revise that section → Verifier again (at most MAX_LOOPS rounds) → thinker reviews, whose critical
concerns must be answered → status "reviewed", otherwise "provisional" with the explicit list of what is open.

State lives in versioned notebook sections (no new table): "proposal" holds the outline, approval, review and
thinker concerns; "proposal_section:<key>" holds each section's draft (with evidence markers) and its
verification. A section the researcher edited is never overwritten without their say-so.
"""
from __future__ import annotations

import json
import math
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from backend.intellectual_rigour.integrity_gate import generate_deterministic_bibliography
from backend.memory import conversation_store as notebook
from backend.research import designer, reviewer, verifier, writer

META = "proposal"
SECTION = "proposal_section:"
MAX_LOOPS = 2
NEEDS_ANSWER = ("critical", "unknown")


# ---------------------------------------------------------------- storage

def _read(thread: str, kind: str) -> Tuple[Optional[Dict[str, Any]], int]:
    sec = notebook.notebook_snapshot(thread).get(kind)
    if not sec:
        return None, 0
    try:
        return json.loads(sec["content"]), sec["version"]
    except Exception:
        return None, sec["version"]


def get_meta(thread: str) -> Dict[str, Any]:
    meta, version = _read(thread, META)
    return {**(meta or {}), "version": version}


def save_meta(thread: str, meta: Dict[str, Any], author: str = "thoth") -> int:
    return notebook.write_section(thread, META, json.dumps({k: v for k, v in meta.items() if k != "version"}), author)


def update_meta(thread: str, author: str = "thoth", **fields: Any) -> Dict[str, Any]:
    meta = get_meta(thread)
    meta.update(fields)
    meta["version"] = save_meta(thread, meta, author)
    return meta


def get_section(thread: str, key: str) -> Optional[Dict[str, Any]]:
    sec, version = _read(thread, SECTION + key)
    return {**sec, "version": version} if sec else None


def save_section(thread: str, sec: Dict[str, Any], author: str) -> Dict[str, Any]:
    body = {k: v for k, v in sec.items() if k != "version"}
    version = notebook.write_section(thread, SECTION + sec["key"], json.dumps(body), author)
    return {**body, "version": version}


# Sections that restate the chosen design: written for one design version, stale when it changes.
DESIGN_DEPENDENT = {"title_abstract", "methods", "expected_outcomes", "limitations_ethics", "timeline"}


def design_version(thread: str) -> int:
    sec = notebook.notebook_snapshot(thread).get("design")
    return sec["version"] if sec else 0


def design_stale(thread: str, sec: Dict[str, Any]) -> str:
    """Why a design-dependent section no longer matches the chosen design ("" if it does). Sections record the design
    version they were written from; older ones are compared by time with the current design version."""
    if sec.get("key") not in DESIGN_DEPENDENT:
        return ""
    hist = notebook.section_history(thread, "design")
    if not hist:
        return ""
    now = hist[-1]
    if sec.get("design_version") is not None:
        return f"written for design v{sec['design_version']}; the design is now v{now['version']}" if sec["design_version"] != now["version"] else ""
    written = sec.get("edited_at") or sec.get("written_at") or 0
    return f"written before design v{now['version']} was chosen" if now["version"] > 1 and written and written < now["created_at"] else ""


def outline_of(thread: str) -> List[Dict[str, str]]:
    return get_meta(thread).get("outline") or writer.default_outline()


def sections(thread: str, outline: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, Any]]:
    out = []
    for s in outline or outline_of(thread):
        if s["key"] == writer.REFERENCES:
            continue
        sec = get_section(thread, s["key"])
        if sec:
            out.append({**sec, "title": s["title"]})
    return out


# ---------------------------------------------------------------- citations and references

def _surname(name: str) -> str:
    parts = str(name or "").replace(",", " ").split()
    return parts[-1] if parts else ""


def author_year(w: Dict[str, Any]) -> str:
    names = [_surname(a) for a in w.get("authors") or [] if _surname(a)]
    year = w.get("year") or "n.d."
    if not names:
        words = str(w.get("title") or "Untitled").split()
        return f"“{' '.join(words[:4])}{'…' if len(words) > 4 else ''}”, {year}"
    who = names[0] if len(names) == 1 else (f"{names[0]} and {names[1]}" if len(names) == 2 else f"{names[0]} et al.")
    return f"{who}, {year}"


def narrative(w: Dict[str, Any]) -> str:
    """Lee et al. (2021): for a witness named in the running text."""
    who, _, year = author_year(w).rpartition(", ")
    return f"{who} ({year})"


def render(md: str, by_id: Dict[str, Dict[str, Any]]) -> str:
    """[W3; W10] → (Lee et al., 2021; Smith, 2019); a witness id in the running text → Lee et al. (2021).
    Unknown ids are left visible, never silently dropped."""
    def sub(m: re.Match) -> str:
        ids = re.split(r"\s*[;,]\s*", m.group(1))
        return "(" + "; ".join(author_year(by_id[i]) if i in by_id else i for i in ids) + ")"
    out = verifier.CITE.sub(sub, verifier.MARKER.sub("", md or ""))
    out = re.sub(r"[ \t]+([.,;:!?])", r"\1", out)
    return re.sub(r"\bW\d+\b", lambda m: narrative(by_id[m.group(0)]) if m.group(0) in by_id else m.group(0), out)


def _body(sec: Dict[str, Any]) -> str:
    v = sec.get("verification")
    return v["final_markdown"] if v else sec.get("draft", "")


def references(thread: str, rf: Dict[str, Any], secs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Only witnesses a verified sentence still cites, formatted by integrity_gate (never by the Writer)."""
    cited: List[str] = []
    for sec in secs if secs is not None else sections(thread):
        if sec.get("verification"):
            cited.extend(sec["verification"].get("cited") or [])
    cited = list(dict.fromkeys(cited))
    by_id = {w["id"]: w for w in rf.get("witnesses") or []}
    sources = [{"id": f"src-{w['id']}", "title": w.get("title"), "authors": w.get("authors") or [], "published_date": w.get("year"),
                "doi": w.get("doi"), "url": w.get("url") or "",
                "extraction_quality": "full" if w.get("access") == "full_text" else "snippet_only"} for w in by_id.values()]
    if not cited:
        return {"markdown": "## References\n\n(No witnesses are cited yet.)", "cited": [], "unresolved": []}
    report, used, unresolved = generate_deterministic_bibliography(" ".join(f"[src-{w}]" for w in cited), sources)
    block = report[report.find("## References"):].strip()
    return {"markdown": block, "cited": [s["id"][4:] for s in used], "unresolved": [u[4:] for u in unresolved]}


def assemble(thread: str, rf: Dict[str, Any], for_reader: bool = True) -> Tuple[str, List[Dict[str, str]]]:
    """The proposal as one Markdown document (citations rendered author-year), plus each section's rendered text."""
    by_id = {w["id"]: w for w in rf.get("witnesses") or []}
    parts, rendered = [], []
    for s in outline_of(thread):
        if s["key"] == writer.REFERENCES:
            parts.append(references(thread, rf)["markdown"])
            continue
        sec = get_section(thread, s["key"])
        text = render(_body(sec), by_id) if sec else f"## {s['title']}\n\n(Not written yet.)"
        rendered.append({"key": s["key"], "title": s["title"], "markdown": text})
        parts.append(text)
    return "\n\n".join(parts), rendered


# ---------------------------------------------------------------- status

def verifier_totals(secs: List[Dict[str, Any]]) -> Dict[str, int]:
    tot: Dict[str, int] = {}
    for sec in secs:
        for k, v in ((sec.get("verification") or {}).get("summary") or {}).items():
            tot[k] = tot.get(k, 0) + int(v)
    return tot


def status(thread: str) -> Dict[str, Any]:
    meta = get_meta(thread)
    outline = outline_of(thread)
    secs = {s["key"]: s for s in sections(thread, outline)}
    gaps: List[str] = []
    for s in outline:
        if s["key"] == writer.REFERENCES:
            continue
        sec = secs.get(s["key"])
        if not sec or not (sec.get("draft") or "").strip():
            gaps.append(f"“{s['title']}” is not written yet.")
        elif not sec.get("verification"):
            gaps.append(f"“{s['title']}” has edits the Verifier has not checked.")
        else:
            sm = sec["verification"]["summary"]
            if sm.get("uncited"):
                gaps.append(f"“{s['title']}”: {sm['uncited']} factual sentence(s) without a source.")
            if sm.get("unchecked"):
                gaps.append(f"“{s['title']}”: {sm['unchecked']} sentence(s) the Verifier could not check.")
            if sm.get("gaps"):
                gaps.append(f"“{s['title']}”: {sm['gaps']} [GAP] marker(s) — the research file lacks something this section needs.")
            why = design_stale(thread, sec)
            if why:
                gaps.append(f"“{s['title']}” was {why}. Regenerate it.")
    rv = meta.get("review")
    open_counts = {"FATAL": 0, "MAJOR": 0, "MINOR": 0}
    review_state = "none"
    if rv and not rv.get("degraded"):
        stale = [k for k, v in (rv.get("seen") or {}).items() if k in secs and secs[k]["version"] != v]
        stale += [k for k in secs if k not in (rv.get("seen") or {})]
        review_state = "stale" if stale else "current"
        open_counts = rv.get("counts") or open_counts
        if open_counts.get("FATAL"):
            gaps.append(f"The Reviewer's {open_counts['FATAL']} FATAL problem(s) are unresolved after {rv.get('loops', 0)} revision round(s).")
        for h in rv.get("held") or []:
            if h.get("fix_in") in ("design", "evidence"):
                where = "a change to the study design (Design tab: Revise the design)" if h["fix_in"] == "design" else "evidence the research file doesn't have"
                gaps.append(f"FATAL {h['id']} needs {where}: {h.get('problem', '')[:140]}")
        if stale:
            gaps.append("Sections changed after the peer review; run the Reviewer again.")
    else:
        gaps.append("The peer Reviewer has not reviewed this proposal." if not rv else "The peer Reviewer could not be reached; no review is on record.")
    advisories: List[str] = []
    if any(s["key"] == "literature" for s in outline):
        # A literature review written from a 15-paper scan is honest only if it says so (vision §5.4). It is advice,
        # not a gap: a scan is not an unresolved check, and the Writer is told to state the coverage as it is.
        t = designer.trial_for_design(thread, writer._section(thread, "design"))
        cov = ((t or {}).get("verdict") or {}).get("coverage") or {}
        if t and cov.get("kind") != "systematic_review":
            advisories.append("The literature review rests on a lightweight scan, not a systematic review; a systematic review "
                              "would make it more defensible.")
    th = meta.get("thinkers") or {}
    concerns = th.get("concerns") or []
    open_c = [c for c in concerns if c["severity"] in NEEDS_ANSWER and not c.get("answer")]
    if not th.get("reviews") or not any(not r.get("degraded") for r in th["reviews"]):
        gaps.append("No thinker has reviewed this proposal.")
    for c in open_c:
        claim = c["claim"] if len(c["claim"]) <= 90 else c["claim"][:88].rstrip() + "…"
        gaps.append(f"{c['thinker_name']}'s {'critical' if c['severity'] == 'critical' else 'unstructured'} concern is unanswered: “{claim}”")
    return {
        "status": "provisional" if gaps else "reviewed", "gaps": gaps, "advisories": advisories,
        "verifier": verifier_totals(list(secs.values())),
        "reviewer": {"state": review_state, "open": open_counts, "loops": (rv or {}).get("loops", 0)},
        "thinkers": {"reviewed": len([r for r in th.get("reviews") or [] if not r.get("degraded")]),
                     "concerns": len(concerns), "need_answer": len([c for c in concerns if c["severity"] in NEEDS_ANSWER]),
                     "open": len(open_c)},
        "sections_written": sum(1 for s in secs.values() if (s.get("draft") or "").strip()),
        "sections_total": len([s for s in outline if s["key"] != writer.REFERENCES]),
    }


def status_line(thread: str) -> str:
    """One line for the conductor's view of the research file (the proposal sections are too long to show it)."""
    st = status(thread)
    return (f"{st['status']}; {st['sections_written']}/{st['sections_total']} sections written; "
            f"{len(st['gaps'])} open item(s)")


# ---------------------------------------------------------------- estimate and approval

def estimate(outline: List[Dict[str, str]], thread: str) -> Dict[str, Any]:
    todo = [s for s in outline if s["key"] != writer.REFERENCES and not (get_section(thread, s["key"]) or {}).get("user_edited")]
    n = len(todo)
    return {"sections": n, "model_calls": f"about {n * 6 + 1}-{n * 12 + 3}",
            "minutes": f"about {max(1, math.ceil(n * 0.5))}-{max(2, math.ceil(n * 1.2))}",
            "cost": "free NVIDIA tier; counts against its rate limit", "revision_rounds": f"at most {MAX_LOOPS}"}


def is_approved(thread: str) -> bool:
    return bool(get_meta(thread).get("approved"))


# ---------------------------------------------------------------- writing

async def write_and_verify(thread: str, s: Dict[str, str], outline: List[Dict[str, str]], rf: Dict[str, Any],
                           earlier: List[Dict[str, str]], revision: Optional[Dict[str, str]] = None,
                           instruction: str = "") -> Optional[Dict[str, Any]]:
    out = await writer.write_section(s, outline, rf, earlier, revision, instruction)
    if out["degraded"]:
        return None
    ver = await verifier.verify_section(out["markdown"], rf["witnesses"], writer.file_keys(rf))
    prev = get_section(thread, s["key"]) or {}
    return save_section(thread, {"key": s["key"], "title": s["title"], "draft": out["markdown"], "author": "thoth",
                                 "design_version": design_version(thread),
                                 "user_edited": False, "verification": ver, "writer_notes": out["notes"],
                                 "written_by": out["written_by"], "revisions": prev.get("revisions", 0) + (1 if revision else 0),
                                 "written_at": time.time()}, "thoth")


def _earlier(thread: str, outline: List[Dict[str, str]], before: str) -> List[Dict[str, str]]:
    out = []
    for s in outline:
        if s["key"] == before:
            break
        sec = get_section(thread, s["key"])
        if sec and _body(sec):
            out.append({"title": s["title"], "markdown": _body(sec)})
    return out


def _to_write(thread: str, outline: List[Dict[str, str]], only_missing: bool) -> List[str]:
    out = []
    for s in outline:
        cur = get_section(thread, s["key"]) if s["key"] != writer.REFERENCES else None
        if s["key"] == writer.REFERENCES or (cur and cur.get("user_edited")) or (only_missing and cur and cur.get("verification")):
            continue
        out.append(s["key"])
    return out


async def write_all(thread: str, outline: List[Dict[str, str]], only_missing: bool = True,
                    one_at_a_time: bool = False) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    """Autopilot: every missing section, then the review. Co-pilot (one_at_a_time): the next missing section only,
    then wait for the researcher's approval of the next one; the review runs once the last one is written."""
    rf = writer.research_file(thread)
    yield "research_file", {"witnesses": len(rf["witnesses"]), "trial": rf["trial_available"], "design": bool(rf["design"])}
    wrote = 0
    for s in outline:
        if s["key"] == writer.REFERENCES:
            continue
        cur = get_section(thread, s["key"])
        if cur and cur.get("user_edited"):
            yield "section_kept", {"key": s["key"], "reason": "has your edits"}
            continue
        if only_missing and cur and cur.get("verification"):
            yield "section_kept", {"key": s["key"], "reason": "already written"}
            continue
        if one_at_a_time and wrote:
            left = _to_write(thread, outline, only_missing)
            yield "awaiting_next", {"next": s["key"], "title": s["title"], "remaining": len(left),
                                    "message": f"Co-pilot: read this section, then approve “{s['title']}” when you're ready."}
            yield "status", status(thread)
            return
        yield "section_writing", {"key": s["key"], "title": s["title"]}
        sec = await write_and_verify(thread, s, outline, rf, _earlier(thread, outline, s["key"]))
        wrote += 1
        if not sec:
            yield "section_failed", {"key": s["key"], "message": "The Writer couldn't be reached; nothing was written in its place."}
            continue
        yield "section_done", {"key": s["key"], "section": sec}
    async for ev in review_loop(thread, rf):
        yield ev
    yield "status", status(thread)


def _similar(a: str, b: str) -> bool:
    from backend.research.librarian import _stems
    x, y = _stems(a), _stems(b)
    return bool(x and y) and len(x & y) / min(len(x), len(y)) >= 0.4


def resolved_since(thread: str, held_now: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A design finding held by the previous review that this review no longer raises was resolved by the design version
    current now, but only if the design changed since it was raised: a Reviewer that merely doesn't repeat it (model
    variance) resolves nothing; that finding is carried forward (carried_held). Append-only, at most 20."""
    prev = get_meta(thread).get("review") or {}
    out = list(prev.get("resolved_held") or [])
    now = design_version(thread)
    for h in prev.get("held") or []:
        if h.get("fix_in") not in ("design", "evidence") or h.get("carried"):
            continue
        if any(n.get("fix_in") == h.get("fix_in") and _similar(n.get("problem", ""), h.get("problem", "")) for n in held_now):
            continue
        if h.get("fix_in") == "design" and h.get("design_version") not in (None, now):
            out.append({**h, "resolved_at": time.time(), "resolved_by_design_version": now})
    return out[-20:]


def carried_held(thread: str, held_now: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Held findings the Reviewer didn't repeat although nothing that could fix them changed: still open."""
    prev = get_meta(thread).get("review") or {}
    now = design_version(thread)
    out = []
    for h in prev.get("held") or []:
        if h.get("fix_in") not in ("design", "evidence"):
            continue
        if any(n.get("fix_in") == h.get("fix_in") and _similar(n.get("problem", ""), h.get("problem", "")) for n in held_now):
            continue
        if h.get("fix_in") == "evidence" or h.get("design_version") in (None, now):
            out.append({**h, "carried": True, "why": (h.get("why") or "") + " (not repeated by this review, but nothing that could fix it has changed)"})
    return out


async def review_loop(thread: str, rf: Optional[Dict[str, Any]] = None) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
    """Reviewer; FATAL → revise the section → Verifier → Reviewer again, at most MAX_LOOPS revision rounds.
    FATALs still open after that stay open (and keep the proposal provisional); they are never dropped."""
    rf = rf or writer.research_file(thread)
    outline = outline_of(thread)
    rounds: List[Dict[str, Any]] = []
    for rnd in range(MAX_LOOPS + 1):
        secs = sections(thread, outline)
        if not secs:
            return
        yield "review_start", {"round": rnd}
        doc, rendered = assemble(thread, rf)
        rv = await reviewer.review(doc, verifier_totals(secs), rendered)
        if rv.get("degraded"):
            update_meta(thread, review={"degraded": True, "at": time.time()})
            yield "review_failed", {"message": "The Reviewer couldn't be reached; no review was made up in its place."}
            return
        fatal = [w for w in rv["weaknesses"] if w["severity"] == "FATAL"]
        by_key = {s["key"]: s for s in secs}
        revisable: Dict[str, List[Dict[str, Any]]] = {}
        held = []
        for w in fatal:
            # Rewording cannot fix a design or evidence problem: those go back to the researcher (Design tab, or
            # more evidence), never to the Writer's revision rounds (docs/features/08; seen live 25 Oct).
            base = {"id": w["id"], "fix_in": w.get("fix_in", "writing"), "problem": w["problem"], "fix": w["fix"], "section": w["section"],
                    "design_version": design_version(thread)}
            if w.get("fix_in", "writing") == "design":
                held.append({**base, "why": "needs a change to the study design"})
            elif w.get("fix_in") == "evidence":
                held.append({**base, "why": "needs evidence the research file doesn't have"})
            elif w["section"] in by_key and not by_key[w["section"]].get("user_edited"):
                revisable.setdefault(w["section"], []).append(w)
            else:
                held.append({**base, "why": "the section has your edits" if w["section"] in by_key else "the passage could not be placed in a section"})
        resolved = resolved_since(thread, held)
        held = held + carried_held(thread, held)
        rv.update(seen={s["key"]: s["version"] for s in secs}, loops=len(rounds), rounds=rounds, held=held, at=time.time(),
                  resolved_held=resolved)
        update_meta(thread, review=rv)
        yield "review_done", {"review": rv, "round": rnd}
        if not revisable or rnd == MAX_LOOPS:
            return
        rounds.append({"round": rnd + 1, "fatal": len(fatal), "revised": list(revisable)})
        for key, ws in revisable.items():
            s = next(o for o in outline if o["key"] == key)
            yield "section_revising", {"key": key, "round": rnd + 1, "problems": [w["problem"] for w in ws]}
            revision = {"previous": _body(by_key[key])[:6000], "severity": "FATAL",
                        "problem": " ".join(w["problem"] for w in ws)[:1500], "fix": " ".join(w["fix"] for w in ws)[:1500]}
            sec = await write_and_verify(thread, s, outline, rf, _earlier(thread, outline, key), revision)
            if sec:
                yield "section_done", {"key": key, "section": sec, "revised": True}
            else:
                yield "section_failed", {"key": key, "message": "The Writer couldn't be reached for the revision."}


# ---------------------------------------------------------------- thinkers

async def thinker_review(thread: str, thinker_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    from backend.thinkers import modes
    rf = writer.research_file(thread)
    doc, _ = assemble(thread, rf)
    ids = thinker_ids or modes.default_reviewers(doc)
    results = await modes.review(thread, ids, "research proposal", doc)
    reviews, concerns = [], []
    for r in results:
        env = r.get("envelope") if isinstance(r.get("envelope"), dict) else None
        reviews.append({"thinker_id": r["thinker_id"], "thinker_name": r["thinker_name"], "review": r.get("review", ""),
                        "degraded": r.get("degraded", False), "verdict": (env or {}).get("verdict"),
                        "would_change_mind_if": (env or {}).get("would_change_mind_if")})
        if r.get("degraded"):
            continue
        if env is None:
            # An unstructured review can't be sorted by severity, so it must be read and answered like a critical one.
            concerns.append({"id": f"{r['thinker_id']}-0", "thinker_id": r["thinker_id"], "thinker_name": r["thinker_name"],
                             "severity": "unknown", "claim": "This review could not be sorted into concerns; read it and reply.", "why": ""})
            continue
        for n, c in enumerate(env.get("concerns") or [], 1):
            if not isinstance(c, dict):
                continue
            sev = c.get("severity") if c.get("severity") in ("critical", "serious", "substantive", "minor") else "unknown"
            concerns.append({"id": f"{r['thinker_id']}-{n}", "thinker_id": r["thinker_id"], "thinker_name": r["thinker_name"],
                             "severity": sev, "claim": str(c.get("claim") or "")[:600], "why": str(c.get("why") or "")[:800]})
    th = {"reviews": reviews, "concerns": concerns, "at": time.time()}
    update_meta(thread, thinkers=th)
    return {**th, "status": status(thread)}


def answer_concern(thread: str, concern_id: str, reply: str) -> Optional[Dict[str, Any]]:
    meta = get_meta(thread)
    th = meta.get("thinkers") or {}
    hit = next((c for c in th.get("concerns") or [] if c["id"] == concern_id), None)
    if not hit:
        return None
    hit.update(answer=reply[:4000], answered_at=time.time())
    update_meta(thread, author="user", thinkers=th)
    notebook.add_turn(thread, "user", f"Reply to {hit['thinker_name']}'s concern on the proposal (“{hit['claim'][:160]}”): {reply[:4000]}",
                      {"kind": "proposal_concern_reply", "concern_id": concern_id, "thinker_id": hit["thinker_id"]})
    return hit


# ---------------------------------------------------------------- export

def export_markdown(thread: str) -> Dict[str, Any]:
    rf = writer.research_file(thread)
    doc, _ = assemble(thread, rf)
    st = status(thread)
    title = re.sub(r"[^a-z0-9]+", "-", (rf.get("hypothesis") or "proposal").lower())[:50].strip("-") or "proposal"
    if st["status"] == "provisional":
        mark = ("> **PROVISIONAL — NOT FULLY REVIEWED.** Thoth could not call this proposal reviewed. Open items:\n"
                + "\n".join(f"> - {g}" for g in st["gaps"]) + "\n\n")
        doc = mark + doc + "\n\n---\n\n*PROVISIONAL draft exported from Thoth. Not fully reviewed; see the open items at the top.*\n"
    v = st["verifier"]
    doc += (f"\n\n<!-- Thoth status: {st['status']}. Verifier: {v.get('checked', 0)} claims checked, {v.get('removed', 0)} removed, "
            f"{v.get('softened', 0)} softened, {v.get('flagged', 0)} flagged. -->\n")
    return {"filename": f"{'PROVISIONAL-' if st['status'] == 'provisional' else ''}{title}.md", "content": doc,
            "status": st["status"], "watermarked": st["status"] == "provisional"}
