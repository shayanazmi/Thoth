"""Threads, projects and retention (docs/features/02-threads-projects-notebook.md).

A chat starts as a thread and becomes a project when a hypothesis is accepted. Both share one id, which every
store already uses as its thread id, so promotion moves nothing: it is read from the notebook (the first
hypothesis version marks it). The server holds the project's state, so a second browser can rebuild it.
Deleting a project removes every row that belongs to it, after a confirmation that lists counts.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from backend.memory import conversation_store as store
from backend.memory import db as _db

WRITABLE = ("question", "hypothesis", "rival_hypothesis")
SOURCE = {"user": "you", "thoth_accepted": "thoth", "thoth": "thoth"}
MAX_MESSAGES = 400


def _conn():
    _db.init_db(_db.DEFAULT_DB_PATH)
    return _db.get_connection(_db.DEFAULT_DB_PATH)


def exists(pid: str) -> bool:
    return bool(_conn().execute("SELECT 1 FROM research_projects WHERE project_id = ?", (pid,)).fetchone())


def promoted_at(pid: str) -> Optional[float]:
    first = store.section_history(pid, "hypothesis")
    return first[0]["created_at"] if first else None


def kind(pid: str) -> str:
    return "project" if promoted_at(pid) else "thread"


def with_context(pid: str, section: str, rationale: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Attach what was known when a hypothesis changed (vision §8.1): the question, for the first version; the
    latest finished trial of the version being replaced, otherwise. It is context, never presented as the reason."""
    from backend.research import store as trials
    r = dict(rationale or {})
    if section != "hypothesis":
        return r
    hist = store.section_history(pid, "hypothesis")
    ctx = list(r.get("context") or [])
    if not hist:
        # The first statement is the original motivation, whoever wrote it; a proposal or an idea keeps its trigger.
        if r.get("trigger") in (None, "", "user_edit", "unknown"):
            r["trigger"] = "initial"
        r["reason"] = r.get("reason") or "First statement of the hypothesis"
        q = store.section_history(pid, "question")
        if q:
            ctx.append({"kind": "question", "ref": {"version": q[-1]["version"]}, "label": q[-1]["content"][:200]})
    else:
        prev = hist[-1]["version"]
        row = _conn().execute("SELECT trial_id FROM trials WHERE thread_id = ? AND hypothesis_version = ? AND status = 'complete' "
                              "ORDER BY created_at DESC LIMIT 1", (pid, prev)).fetchone()
        t = trials.get_trial(row[0]) if row else None
        if t and t.get("verdict"):
            v = (t["verdict"].get("overall") or {}).get("verdict") or "no verdict"
            ctx.append({"kind": "trial_verdict", "ref": {"trial_id": t["trial_id"], "hypothesis_version": prev},
                        "label": f"Latest trial for v{prev}: {v.replace('_', ' ')}"})
    r["context"] = ctx
    return r


def write(pid: str, section: str, value: str, rationale: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The researcher's own edit of the question, the hypothesis or a rival (a new version, authored by them),
    with why it changed (optional; a plain edit says "Edited by you")."""
    if section not in WRITABLE:
        raise ValueError(f"only {', '.join(WRITABLE)} can be written here")
    value = (value or "").strip()
    if not value:
        raise ValueError("empty value")
    r = dict(rationale or {})
    r.setdefault("trigger", "user_edit")
    r.setdefault("source", "you")
    r = with_context(pid, section, r)
    r["reason"] = r.get("reason") or "Edited by you"
    version = store.write_section(pid, section, value[:4000], "user", rationale=r)
    return {"section": section, "value": value, "version": version, "kind": kind(pid)}


HISTORY_KINDS = ("question", "hypothesis", "rival_hypothesis", "design")


def history(pid: str, section: str) -> Dict[str, Any]:
    """Every version with why it changed, and the original motivation (version 1 and the question it answered)."""
    if section not in HISTORY_KINDS:
        raise ValueError(f"history is kept for {', '.join(HISTORY_KINDS)}")
    rows = store.section_history(pid, section)
    out, prev = [], None
    for v in rows:
        content: Any = v["content"]
        item = {"version": v["version"], "author": v["author"], "source": SOURCE.get(v["author"], v["author"]),
                "at": int(v["created_at"] * 1000), "rationale": v.get("rationale") or {}}
        if section == "design":
            try:
                content = json.loads(content)
            except ValueError:
                pass
            if isinstance(content, dict) and isinstance(prev, dict):
                item["changed_fields"] = sorted(k for k in set(content) | set(prev)
                                                if k not in ("version", "author") and content.get(k) != prev.get(k))
        else:
            item["previous_content"] = prev
        item["content"] = content
        out.append(item)
        prev = content
    question = store.section_history(pid, "question")
    original = None
    if out:
        first_at = rows[0]["created_at"]
        asked = [q for q in question if q["created_at"] <= first_at]
        original = {**out[0], "question": (asked[-1] if asked else (question[0] if question else {})).get("content", "")}
    return {"project_id": pid, "kind": section, "original": original, "versions": out}


def _messages(pid: str) -> List[Dict[str, Any]]:
    """The main conversation as the chat shows it (thinker one-to-one rooms are separate threads)."""
    out = []
    for t in store.recent_turns(pid, MAX_MESSAGES):
        role = {"user": "user", "assistant": "thoth", "thinker": "thinker"}.get(t["role"])
        if not role:
            continue
        msg = {"role": role, "text": t["content"], "at": int(t["created_at"] * 1000)}
        if role == "thinker":
            msg["thinker"] = {"id": t["meta"].get("thinker_id"), "name": t["meta"].get("thinker_name") or "A thinker"}
        out.append(msg)
    return out


# ---------------------------------------------------------------- hypothesis versions, markers, rivals (feature 04)

def current_hypothesis(pid: str) -> Optional[Dict[str, Any]]:
    hist = store.section_history(pid, "hypothesis")
    return {"version": hist[-1]["version"], "text": hist[-1]["content"]} if hist else None


def version_of(pid: str, text: str) -> Optional[int]:
    """The latest version whose text is exactly this hypothesis (None if it was never written to the project)."""
    clean = (text or "").strip()
    hits = [v["version"] for v in store.section_history(pid, "hypothesis") if v["content"].strip() == clean]
    return hits[-1] if hits else None


async def markers(pid: str) -> Dict[str, Any]:
    """Strength markers of the current hypothesis, computed once per version and kept in the notebook."""
    from backend.research import hypothesis
    cur = current_hypothesis(pid)
    if not cur:
        return {**hypothesis.unchecked(), "version": None, "text": ""}
    cached = store.notebook_snapshot(pid).get("hypothesis_markers")
    if cached:
        data = json.loads(cached["content"])
        if data.get("version") == cur["version"] and data.get("checked") and data.get("rules") == hypothesis.RULES_VERSION:
            return data
    data = {**await hypothesis.markers(cur["text"]), "version": cur["version"], "text": cur["text"]}
    if data["checked"]:
        store.write_section(pid, "hypothesis_markers", json.dumps(data), "thoth")
    return data


def _retired(pid: str) -> List[str]:
    sec = store.notebook_snapshot(pid).get("rivals_retired")
    return json.loads(sec["content"]) if sec else []


def rivals(pid: str) -> List[str]:
    """Parked rival hypotheses: every rival ever written, minus retired ones and the current main hypothesis."""
    main = (current_hypothesis(pid) or {}).get("text")
    retired = set(_retired(pid))
    return [r for r in dict.fromkeys(v["content"] for v in store.section_history(pid, "rival_hypothesis"))
            if r not in retired and r != main]


def retire_rival(pid: str, text: str) -> List[str]:
    if text not in rivals(pid):
        raise ValueError("not a parked rival")
    store.write_section(pid, "rivals_retired", json.dumps(_retired(pid) + [text]), "user",
                        rationale={"trigger": "user_edit", "source": "you", "reason": "Retired by you"})
    return rivals(pid)


def swap(pid: str, text: str) -> Dict[str, Any]:
    """The rival becomes the main hypothesis (a new version); the old main is parked as a rival."""
    if text not in rivals(pid):
        raise ValueError("not a parked rival")
    old = current_hypothesis(pid)
    if old:
        store.write_section(pid, "rival_hypothesis", old["text"], "user",
                            rationale={"trigger": "rival_swap", "source": "you", "reason": "Parked when a rival was swapped in"})
    why = with_context(pid, "hypothesis", {"trigger": "rival_swap", "source": "you",
                                           "reason": f"Swapped in a parked rival (it replaced v{old['version']})" if old else "Swapped in a parked rival",
                                           "decision_ref": {"kind": "rival", "id": text[:120]}})
    store.write_section(pid, "hypothesis", text, "user", rationale=why)
    retired = _retired(pid)
    if old and old["text"] in retired:
        store.write_section(pid, "rivals_retired", json.dumps([r for r in retired if r != old["text"]]), "user")
    return state(pid)


# ---------------------------------------------------------------- Autopilot / Co-pilot (docs/features/02)

MODES = ("copilot", "autopilot")
STEPS = ("subclaims", "screening", "proposal")


def get_mode(pid: str) -> Dict[str, Any]:
    """The project's mode and per-step overrides. Co-pilot unless the researcher chose otherwise.
    Either way, heavy runs still need the researcher's up-front approval with an estimate."""
    sec = store.notebook_snapshot(pid).get("mode")
    data = json.loads(sec["content"]) if sec else {}
    mode = data.get("mode") if data.get("mode") in MODES else "copilot"
    overrides = {k: v for k, v in (data.get("step_overrides") or {}).items() if k in STEPS and v in MODES}
    return {"mode": mode, "step_overrides": overrides, "effective": {s: overrides.get(s, mode) for s in STEPS}}


def set_mode(pid: str, mode: str, step_overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    overrides = step_overrides or {}
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    bad = [k for k, v in overrides.items() if k not in STEPS or v not in MODES]
    if bad:
        raise ValueError(f"unknown step or mode in overrides: {', '.join(bad)}")
    store.write_section(pid, "mode", json.dumps({"mode": mode, "step_overrides": overrides}), "user")
    return get_mode(pid)


def step_mode(pid: str, step: str) -> str:
    return get_mode(pid)["effective"][step]


def state(pid: str) -> Dict[str, Any]:
    hyp = store.section_history(pid, "hypothesis")
    rivals_now = rivals(pid)
    question = store.section_history(pid, "question")
    row = _conn().execute("SELECT title FROM research_projects WHERE project_id = ?", (pid,)).fetchone()
    return {
        "project_id": pid, "title": row[0] if row else "", "kind": "project" if hyp else "thread",
        "promoted_at": hyp[0]["created_at"] if hyp else None,
        "question": question[-1]["content"] if question else "",
        "hypothesis": [{"text": v["content"], "version": v["version"],
                        "source": (v.get("rationale") or {}).get("source") or SOURCE.get(v["author"], v["author"]),
                        "at": int(v["created_at"] * 1000), "reason": (v.get("rationale") or {}).get("reason") or "",
                        "trigger": (v.get("rationale") or {}).get("trigger") or "",
                        "evidence": (v.get("rationale") or {}).get("evidence") or [],
                        "context": (v.get("rationale") or {}).get("context") or [],
                        "previous_version": (v.get("rationale") or {}).get("previous_version")} for v in hyp],
        "rivals": rivals_now, "messages": _messages(pid), "mode": get_mode(pid),
    }


# ---------------------------------------------------------------- retention

def _threads(pid: str) -> str:
    """WHERE clause for every thread of a project: the main one and its thinker rooms (pid::room::<thinker>).
    An exact prefix match: LIKE would treat the "_" in project ids as a wildcard."""
    return "(thread_id = ? OR substr(thread_id, 1, ?) = ?)"


def _args(pid: str):
    return (pid, len(pid) + 2, f"{pid}::")


LABELS = [("papers", "paper", "papers"), ("trials", "trial", "trials"), ("systematic_reviews", "systematic review", "systematic reviews"),
          ("review_records", "screening record", "screening records"),
          ("review_searches", "logged search", "logged searches"), ("messages", "message", "messages"),
          ("notebook_entries", "notebook entry", "notebook entries"), ("thinker_memories", "thinker memory", "thinker memories")]


def footprint(pid: str) -> Dict[str, Any]:
    c = _conn()
    one = lambda sql, args: c.execute(sql, args).fetchone()[0]
    w, a = _threads(pid), _args(pid)
    counts = {
        "messages": one(f"SELECT COUNT(*) FROM conversation_turns WHERE {w}", a),
        "notebook_entries": one(f"SELECT COUNT(*) FROM notebook_sections WHERE {w}", a),
        "proposals": one(f"SELECT COUNT(*) FROM conductor_proposals WHERE {w}", a),
        "thinker_memories": one(f"SELECT COUNT(*) FROM thinker_memory WHERE {w}", a),
        "trials": one(f"SELECT COUNT(*) FROM trials WHERE {w}", a),
        "papers": one(f"SELECT COUNT(*) FROM trial_papers WHERE trial_id IN (SELECT trial_id FROM trials WHERE {w})", a),
        "systematic_reviews": one(f"SELECT COUNT(*) FROM sys_reviews WHERE {w}", a),
        "review_records": one(f"SELECT COUNT(*) FROM sys_review_records WHERE review_id IN (SELECT review_id FROM sys_reviews WHERE {w})", a),
        "review_searches": one(f"SELECT COUNT(*) FROM sys_review_searches WHERE review_id IN (SELECT review_id FROM sys_reviews WHERE {w})", a),
    }
    parts = [f"{counts[k]} {one_ if counts[k] == 1 else many}" for k, one_, many in LABELS if counts[k]]
    return {"project_id": pid, "counts": counts, "summary": ", ".join(parts) or "nothing stored yet"}


def delete(pid: str) -> Dict[str, Any]:
    """Remove everything that belongs to the project, in one transaction. Returns what was removed."""
    removed = footprint(pid)
    w, a = _threads(pid), _args(pid)
    c = _conn()
    with c:
        c.execute(f"DELETE FROM trial_papers WHERE trial_id IN (SELECT trial_id FROM trials WHERE {w})", a)
        c.execute(f"DELETE FROM sys_review_records WHERE review_id IN (SELECT review_id FROM sys_reviews WHERE {w})", a)
        c.execute(f"DELETE FROM sys_review_searches WHERE review_id IN (SELECT review_id FROM sys_reviews WHERE {w})", a)
        for table in ("conversation_turns", "thread_summaries", "conductor_proposals", "notebook_sections", "thinker_memory", "trials", "sys_reviews"):
            c.execute(f"DELETE FROM {table} WHERE {w}", a)
        c.execute("DELETE FROM research_projects WHERE project_id = ?", (pid,))
    return removed
