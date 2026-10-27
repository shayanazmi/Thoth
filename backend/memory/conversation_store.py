"""Conversation core storage (docs/features/01, 02).

Turns, rolling summaries, conductor proposals/offers and versioned notebook
sections. The DB path is resolved at call time from ``backend.memory.db`` so
scenario fixtures that reload that module land on their own tmp database.
"""
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


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------- turns

def add_turn(thread_id: str, role: str, content: str, meta: Optional[Dict[str, Any]] = None) -> str:
    turn_id = _id("turn")
    conn = _conn()
    with conn:
        conn.execute(
            "INSERT INTO conversation_turns (turn_id, thread_id, role, content, meta_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (turn_id, thread_id, role, content, json.dumps(meta or {}), time.time()),
        )
    return turn_id


def recent_turns(thread_id: str, limit: int = 12) -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        "SELECT role, content, meta_json, created_at FROM conversation_turns WHERE thread_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
        (thread_id, limit),
    ).fetchall()
    return [{"role": r[0], "content": r[1], "meta": json.loads(r[2] or "{}"), "created_at": r[3]} for r in reversed(rows)]


def count_turns(thread_id: str) -> int:
    conn = _conn()
    return conn.execute("SELECT COUNT(*) FROM conversation_turns WHERE thread_id = ?", (thread_id,)).fetchone()[0]


def search_turns(thread_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    words = [w for w in query.lower().split() if len(w) > 3][:5] or [query.lower()]
    conn = _conn()
    clause = " OR ".join("LOWER(content) LIKE ?" for _ in words)
    rows = conn.execute(
        f"SELECT role, content FROM conversation_turns WHERE thread_id = ? AND ({clause}) ORDER BY created_at DESC LIMIT ?",
        (thread_id, *[f"%{w}%" for w in words], limit),
    ).fetchall()
    return [{"role": r[0], "content": r[1][:400]} for r in rows]


# ---------------------------------------------------------------- summaries

def get_summary(thread_id: str) -> Dict[str, Any]:
    conn = _conn()
    row = conn.execute("SELECT summary, turns_covered FROM thread_summaries WHERE thread_id = ?", (thread_id,)).fetchone()
    return {"summary": row[0], "turns_covered": row[1]} if row else {"summary": "", "turns_covered": 0}


def set_summary(thread_id: str, summary: str, turns_covered: int) -> None:
    conn = _conn()
    with conn:
        conn.execute(
            "INSERT INTO thread_summaries (thread_id, summary, turns_covered, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(thread_id) DO UPDATE SET summary = excluded.summary, turns_covered = excluded.turns_covered, updated_at = excluded.updated_at",
            (thread_id, summary, turns_covered, time.time()),
        )


# ---------------------------------------------------------------- proposals and offers

def add_proposal(thread_id: str, kind: str, payload: Dict[str, Any]) -> str:
    proposal_id = _id("prop")
    conn = _conn()
    with conn:
        conn.execute(
            "INSERT INTO conductor_proposals (proposal_id, thread_id, kind, payload_json, status, created_at) VALUES (?, ?, ?, ?, 'open', ?)",
            (proposal_id, thread_id, kind, json.dumps(payload), time.time()),
        )
    return proposal_id


def open_proposals(thread_id: str) -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        "SELECT proposal_id, kind, payload_json, created_at FROM conductor_proposals WHERE thread_id = ? AND status = 'open' ORDER BY created_at",
        (thread_id,),
    ).fetchall()
    return [{"proposal_id": r[0], "kind": r[1], "payload": json.loads(r[2]), "created_at": r[3]} for r in rows]


def recent_proposals(thread_id: str, kind: str, limit: int = 5) -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        "SELECT proposal_id, payload_json, status, created_at FROM conductor_proposals WHERE thread_id = ? AND kind = ? ORDER BY created_at DESC LIMIT ?",
        (thread_id, kind, limit),
    ).fetchall()
    return [{"proposal_id": r[0], "payload": json.loads(r[1]), "status": r[2], "created_at": r[3]} for r in rows]


def get_proposal(proposal_id: str) -> Optional[Dict[str, Any]]:
    conn = _conn()
    r = conn.execute(
        "SELECT proposal_id, thread_id, kind, payload_json, status FROM conductor_proposals WHERE proposal_id = ?",
        (proposal_id,),
    ).fetchone()
    return {"proposal_id": r[0], "thread_id": r[1], "kind": r[2], "payload": json.loads(r[3]), "status": r[4]} if r else None


def resolve_proposal(proposal_id: str, status: str) -> None:
    conn = _conn()
    with conn:
        conn.execute(
            "UPDATE conductor_proposals SET status = ?, resolved_at = ? WHERE proposal_id = ?",
            (status, time.time(), proposal_id),
        )


# ---------------------------------------------------------------- notebook

def write_section(thread_id: str, kind: str, content: str, author: str) -> int:
    conn = _conn()
    with conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM notebook_sections WHERE thread_id = ? AND kind = ?",
            (thread_id, kind),
        ).fetchone()
        version = (row[0] or 0) + 1
        conn.execute(
            "INSERT INTO notebook_sections (section_id, thread_id, kind, version, content, author, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_id("sec"), thread_id, kind, version, content, author, time.time()),
        )
    return version


def notebook_snapshot(thread_id: str) -> Dict[str, Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        "SELECT kind, content, version, author FROM notebook_sections s WHERE thread_id = ? AND version = "
        "(SELECT MAX(version) FROM notebook_sections WHERE thread_id = s.thread_id AND kind = s.kind)",
        (thread_id,),
    ).fetchall()
    return {r[0]: {"content": r[1], "version": r[2], "author": r[3]} for r in rows}


# ---------------------------------------------------------------- thinker memory

def get_thinker_memory(thread_id: str, thinker_id: str) -> Dict[str, Any]:
    conn = _conn()
    row = conn.execute(
        "SELECT stance, changes FROM thinker_memory WHERE thread_id = ? AND thinker_id = ?",
        (thread_id, thinker_id),
    ).fetchone()
    return {"stance": row[0], "changes": row[1]} if row else {"stance": "", "changes": 0}


def set_thinker_memory(thread_id: str, thinker_id: str, stance: str, changed: bool) -> None:
    conn = _conn()
    with conn:
        conn.execute(
            "INSERT INTO thinker_memory (thread_id, thinker_id, stance, changes, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(thread_id, thinker_id) DO UPDATE SET stance = excluded.stance, "
            "changes = thinker_memory.changes + ?, updated_at = excluded.updated_at",
            (thread_id, thinker_id, stance, int(changed), time.time(), int(changed)),
        )


def section_history(thread_id: str, kind: str) -> List[Dict[str, Any]]:
    """Every version of one notebook section, oldest first."""
    conn = _conn()
    rows = conn.execute(
        "SELECT content, version, author, created_at FROM notebook_sections WHERE thread_id = ? AND kind = ? ORDER BY version",
        (thread_id, kind),
    ).fetchall()
    return [{"content": r[0], "version": r[1], "author": r[2], "created_at": r[3]} for r in rows]
