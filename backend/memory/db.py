# Thoth · Developed by Shayan Azmi
"""SQLite storage. The schema lives in database/schema.sql and is applied (idempotently) at startup.

Set THOTH_DB_PATH to use another file; the default is database/thoth.db.
"""
import os
import sqlite3
from typing import Optional

_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCHEMA_PATH = os.path.join(_ROOT_DIR, "database", "schema.sql")
DEFAULT_DB_PATH = os.environ.get("THOTH_DB_PATH") or os.path.join(_ROOT_DIR, "database", "thoth.db")


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# Databases whose schema is already in place in this process: running the schema script on every store call
# would be wasted work (a review inserts hundreds of rows). Keyed by absolute path; a file that has gone is set up again.
_READY: set = set()


def init_db(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    key = os.path.abspath(db_path)
    if key in _READY and os.path.exists(key):
        return get_connection(db_path)
    conn = get_connection(db_path)
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    _READY.add(key)
    return conn


def save_idea_db(idea_data: dict, db_path: str = DEFAULT_DB_PATH) -> dict:
    import json
    import datetime
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO research_ideas (
                idea_id, session_id, title, description, hypothesis, status,
                thinker_id, thinker_critique, unresolved_objections_json,
                parent_idea_id, revision_version, revision_notes, brief_id,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(idea_id) DO UPDATE SET
                session_id=excluded.session_id,
                title=excluded.title,
                description=excluded.description,
                hypothesis=excluded.hypothesis,
                status=excluded.status,
                thinker_id=excluded.thinker_id,
                thinker_critique=excluded.thinker_critique,
                unresolved_objections_json=excluded.unresolved_objections_json,
                parent_idea_id=excluded.parent_idea_id,
                revision_version=excluded.revision_version,
                revision_notes=excluded.revision_notes,
                brief_id=excluded.brief_id,
                updated_at=excluded.updated_at;
        """, (
            idea_data["idea_id"],
            idea_data.get("session_id", ""),
            idea_data["title"],
            idea_data.get("description", ""),
            idea_data["hypothesis"],
            idea_data.get("status", "TENTATIVE"),
            idea_data.get("thinker_id", ""),
            idea_data.get("thinker_critique", ""),
            json.dumps(idea_data.get("unresolved_objections", [])),
            idea_data.get("parent_idea_id"),
            idea_data.get("revision_version", 1),
            idea_data.get("revision_notes", ""),
            idea_data.get("brief_id"),
            idea_data.get("created_at", now_iso),
            idea_data.get("updated_at", now_iso),
        ))
    return get_idea_db(idea_data["idea_id"], db_path=db_path)


def get_idea_db(idea_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM research_ideas WHERE idea_id = ?;", (idea_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    d["unresolved_objections"] = json.loads(d.get("unresolved_objections_json") or "[]")
    return d


def list_ideas_db(
    session_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db_path: str = DEFAULT_DB_PATH
) -> list:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    query = "SELECT * FROM research_ideas WHERE 1=1"
    params = []
    if session_id:
        query += " AND session_id = ?"
        params.append(session_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["unresolved_objections"] = json.loads(d.get("unresolved_objections_json") or "[]")
        results.append(d)
    return results


# ==========================================
# ==========================================

def save_project_db(
    project_id: str,
    title: str,
    description: str = "",
    session_id: str = "",
    status: str = "ACTIVE",
    metadata: Optional[dict] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    import datetime
    import json
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    meta_json = json.dumps(metadata or {})

    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT created_at FROM research_projects WHERE project_id = ?;", (project_id,))
        row = cursor.fetchone()
        created_at = row["created_at"] if row else now_iso

        cursor.execute("""
            INSERT INTO research_projects (project_id, title, description, session_id, status, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                session_id = excluded.session_id,
                status = excluded.status,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at;
        """, (project_id, title, description, session_id, status, meta_json, created_at, now_iso))

    return {
        "project_id": project_id,
        "title": title,
        "description": description,
        "session_id": session_id,
        "status": status,
        "metadata": metadata or {},
        "created_at": created_at,
        "updated_at": now_iso,
    }


def list_projects_db(
    session_id: Optional[str] = None,
    status: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()

    query = "SELECT * FROM research_projects WHERE 1=1"
    params = []
    if session_id:
        query += " AND session_id = ?"
        params.append(session_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY updated_at DESC;"

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["metadata"] = json.loads(d.get("metadata_json") or "{}")
        except Exception:
            d["metadata"] = {}
        out.append(d)
    return out


# ==============================================================================
# ==============================================================================


# ==============================================================================
# ==============================================================================


# ==============================================================================
# ==============================================================================


# ==============================================================================
# ==============================================================================


# ==============================================================================
# ==============================================================================


