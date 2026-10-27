"""Persistence for trials and their papers (tables in backend/memory/db.py, migration 008)."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from backend.memory import db as _db


def _conn():
    path = _db.DEFAULT_DB_PATH
    _db.init_db(path)
    return _db.get_connection(path)


def create_trial(thread_id: str, hypothesis: str, subclaims: List[Dict[str, Any]]) -> str:
    trial_id = f"trial_{uuid.uuid4().hex[:12]}"
    now = time.time()
    with _conn() as c:
        c.execute("INSERT INTO trials (trial_id, thread_id, hypothesis, subclaims_json, status, created_at, updated_at) "
                  "VALUES (?, ?, ?, ?, 'planned', ?, ?)", (trial_id, thread_id, hypothesis, json.dumps(subclaims), now, now))
    return trial_id


def update_trial(trial_id: str, **fields: Any) -> None:
    cols = {k: (json.dumps(v) if k.endswith("_json") else v) for k, v in fields.items()}
    cols["updated_at"] = time.time()
    with _conn() as c:
        c.execute(f"UPDATE trials SET {', '.join(f'{k} = ?' for k in cols)} WHERE trial_id = ?", (*cols.values(), trial_id))


def claim_for_run(trial_id: str) -> bool:
    """Atomically move a planned trial to running. False if it was not planned (already run or unknown)."""
    with _conn() as c:
        cur = c.execute("UPDATE trials SET status = 'running', updated_at = ? WHERE trial_id = ? AND status = 'planned'",
                        (time.time(), trial_id))
        return cur.rowcount == 1


def claim_for_reanalysis(trial_id: str) -> bool:
    """Atomically move a complete trial to 'reanalysing'. False if it isn't complete (running, planned, busy)."""
    with _conn() as c:
        cur = c.execute("UPDATE trials SET status = 'reanalysing', updated_at = ? WHERE trial_id = ? AND status = 'complete'",
                        (time.time(), trial_id))
        return cur.rowcount == 1


def get_trial(trial_id: str) -> Optional[Dict[str, Any]]:
    c = _conn()
    r = c.execute("SELECT trial_id, thread_id, hypothesis, subclaims_json, status, strategy_json, verdict_json, adjacent_json "
                  "FROM trials WHERE trial_id = ?", (trial_id,)).fetchone()
    if not r:
        return None
    return {"trial_id": r[0], "thread_id": r[1], "hypothesis": r[2], "subclaims": json.loads(r[3]), "status": r[4],
            "strategy": json.loads(r[5]), "verdict": json.loads(r[6]), "adjacent": json.loads(r[7]),
            "papers": list_papers(trial_id)}


def add_paper(trial_id: str, meta: Dict[str, Any]) -> str:
    paper_id = f"pap_{uuid.uuid4().hex[:10]}"
    with _conn() as c:
        c.execute("INSERT INTO trial_papers (paper_id, trial_id, meta_json, created_at) VALUES (?, ?, ?, ?)",
                  (paper_id, trial_id, json.dumps(meta), time.time()))
    return paper_id


def update_paper(paper_id: str, **fields: Any) -> None:
    cols = {k: (json.dumps(v) if k.endswith("_json") else v) for k, v in fields.items()}
    with _conn() as c:
        c.execute(f"UPDATE trial_papers SET {', '.join(f'{k} = ?' for k in cols)} WHERE paper_id = ?", (*cols.values(), paper_id))


def _paper(r) -> Dict[str, Any]:
    return {"paper_id": r[0], "trial_id": r[1], "meta": json.loads(r[2]), "access": r[3], "text_source": r[4],
            "record": json.loads(r[5]), "row": json.loads(r[6]), "weight": r[7], "i_say_user": r[8], "status": r[9]}


_COLS = "paper_id, trial_id, meta_json, access, text_source, record_json, row_json, weight, i_say_user, status"


def get_paper(paper_id: str) -> Optional[Dict[str, Any]]:
    r = _conn().execute(f"SELECT {_COLS} FROM trial_papers WHERE paper_id = ?", (paper_id,)).fetchone()
    return _paper(r) if r else None


def list_papers(trial_id: str) -> List[Dict[str, Any]]:
    rows = _conn().execute(f"SELECT {_COLS} FROM trial_papers WHERE trial_id = ? ORDER BY created_at, rowid", (trial_id,)).fetchall()
    return [_paper(r) for r in rows]


def reconcile_orphaned_trials() -> int:
    """At startup, nothing can still be running: trials left 'running' by a previous process are 'stopped'.
    A re-analysis cut short goes back to 'complete': its records are intact and "Edit sub-claims" can be redone."""
    with _conn() as c:
        c.execute("UPDATE trials SET status = 'complete', updated_at = ? WHERE status = 'reanalysing'", (time.time(),))
        return c.execute("UPDATE trials SET status = 'stopped', updated_at = ? WHERE status = 'running'", (time.time(),)).rowcount
