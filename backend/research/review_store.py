"""Persistence for systematic reviews (tables in backend/memory/db.py, migration 010)."""
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


def create(thread_id: str, hypothesis: str, protocol: Dict[str, Any], subclaims: List[Dict[str, Any]]) -> str:
    rid = f"rev_{uuid.uuid4().hex[:12]}"
    now = time.time()
    with _conn() as c:
        c.execute("INSERT INTO sys_reviews (review_id, thread_id, hypothesis, protocol_json, subclaims_json, status, stage, created_at, updated_at) "
                  "VALUES (?, ?, ?, ?, ?, 'planned', 'planned', ?, ?)", (rid, thread_id, hypothesis, json.dumps(protocol), json.dumps(subclaims), now, now))
    return rid


def update(review_id: str, **fields: Any) -> None:
    cols = {k: (json.dumps(v) if k.endswith("_json") else v) for k, v in fields.items()}
    cols["updated_at"] = time.time()
    with _conn() as c:
        c.execute(f"UPDATE sys_reviews SET {', '.join(f'{k} = ?' for k in cols)} WHERE review_id = ?", (*cols.values(), review_id))


def claim(review_id: str) -> bool:
    """Atomically move a planned review to running. Runs once."""
    with _conn() as c:
        return c.execute("UPDATE sys_reviews SET status = 'running', updated_at = ? WHERE review_id = ? AND status = 'planned'",
                         (time.time(), review_id)).rowcount == 1


def get(review_id: str) -> Optional[Dict[str, Any]]:
    r = _conn().execute("SELECT review_id, thread_id, hypothesis, protocol_json, subclaims_json, mode, status, stage, trial_id, note "
                        "FROM sys_reviews WHERE review_id = ?", (review_id,)).fetchone()
    if not r:
        return None
    return {"review_id": r[0], "thread_id": r[1], "hypothesis": r[2], "protocol": json.loads(r[3]), "subclaims": json.loads(r[4]),
            "mode": r[5], "status": r[6], "stage": r[7], "trial_id": r[8], "note": r[9]}


def latest(thread_id: str) -> Optional[str]:
    r = _conn().execute("SELECT review_id FROM sys_reviews WHERE thread_id = ? AND status != 'planned' ORDER BY created_at DESC LIMIT 1",
                        (thread_id,)).fetchone()
    return r[0] if r else None


def add_record(review_id: str, meta: Dict[str, Any], source: str, dup_of: Optional[str] = None) -> str:
    rec_id = f"rec_{uuid.uuid4().hex[:10]}"
    with _conn() as c:
        c.execute("INSERT INTO sys_review_records (record_id, review_id, meta_json, source, dup_of, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                  (rec_id, review_id, json.dumps(meta), source, dup_of, time.time()))
    return rec_id


def update_record(record_id: str, **fields: Any) -> None:
    cols = {k: (json.dumps(v) if k.endswith("_json") else v) for k, v in fields.items()}
    with _conn() as c:
        c.execute(f"UPDATE sys_review_records SET {', '.join(f'{k} = ?' for k in cols)} WHERE record_id = ?", (*cols.values(), record_id))


def records(review_id: str) -> List[Dict[str, Any]]:
    rows = _conn().execute("SELECT record_id, meta_json, source, dup_of, screening_json, ft_access, paper_id FROM sys_review_records "
                           "WHERE review_id = ? ORDER BY created_at, rowid", (review_id,)).fetchall()
    return [{"record_id": r[0], "meta": json.loads(r[1]), "source": r[2], "dup_of": r[3], "screening": json.loads(r[4] or "{}"),
             "ft_access": r[5], "paper_id": r[6]} for r in rows]


def get_record(record_id: str) -> Optional[Dict[str, Any]]:
    r = _conn().execute("SELECT review_id FROM sys_review_records WHERE record_id = ?", (record_id,)).fetchone()
    return next((x for x in records(r[0]) if x["record_id"] == record_id), None) if r else None


def reconcile_orphaned() -> int:
    with _conn() as c:
        return c.execute("UPDATE sys_reviews SET status = 'stopped', updated_at = ? WHERE status = 'running'", (time.time(),)).rowcount
