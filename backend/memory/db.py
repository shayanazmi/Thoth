import os
import sqlite3
from typing import Optional

DEFAULT_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "store.db"))


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """
    Creates and returns a sqlite3 connection with WAL mode enabled.
    """
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """
    Initializes or migrates the SQLite schema. Safe to call repeatedly.
    Creates notes, notes_fts (FTS5), embeddings, edges, sessions, and reports tables.
    """
    conn = get_connection(db_path)
    with conn:
        # 1. Notes Metadata Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                note_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                created TEXT NOT NULL,
                confidence REAL DEFAULT 1.0
            );
        """)

        # 2. FTS5 Virtual Table for Keyword BM25 Search
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                note_id UNINDEXED,
                body
            );
        """)

        # 3. Vector Embeddings Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                note_id TEXT PRIMARY KEY,
                vector BLOB NOT NULL,
                dim INTEGER NOT NULL
            );
        """)

        # 4. Knowledge Graph Edges Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                source_note TEXT NOT NULL,
                relation TEXT NOT NULL CHECK (relation IN ('cites', 'supports', 'contradicts', 'part_of', 'defines', 'related')),
                target_note TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                PRIMARY KEY (source_note, relation, target_note)
            );
        """)

        # 5. Sessions Table (for application session history)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                summary TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}'
            );
        """)

        # 6. Reports Table (for persisted research reports)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                report_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                score REAL DEFAULT 0.0,
                verifier_feedback TEXT DEFAULT '',
                mindmap TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );
        """)

    return conn


def save_session(
    session_id: str,
    title: str,
    summary: str = "",
    metadata: Optional[dict] = None,
    db_path: str = DEFAULT_DB_PATH
) -> dict:
    """Inserts or updates a session in the database."""
    import datetime
    import json
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    meta_json = json.dumps(metadata or {})
    
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO sessions (session_id, title, created_at, updated_at, summary, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                title=excluded.title,
                updated_at=excluded.updated_at,
                summary=excluded.summary,
                metadata=excluded.metadata;
        """, (session_id, title, now_iso, now_iso, summary, meta_json))
    
    return get_session(session_id, db_path=db_path)


def get_session(session_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    """Retrieves a session by ID."""
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE session_id = ?;", (session_id,))
    row = cursor.fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        data["metadata"] = json.loads(data.get("metadata") or "{}")
    except Exception:
        data["metadata"] = {}
    return data


def list_sessions(limit: Optional[int] = None, db_path: str = DEFAULT_DB_PATH) -> list:
    """Lists all sessions ordered by updated_at descending, optionally limited."""
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    query = "SELECT * FROM sessions ORDER BY updated_at DESC"
    params = []
    if limit is not None and limit > 0:
        query += " LIMIT ?"
        params.append(limit)
    cursor.execute(query + ";", params)
    rows = cursor.fetchall()
    results = []
    for r in rows:
        d = dict(r)
        try:
            d["metadata"] = json.loads(d.get("metadata") or "{}")
        except Exception:
            d["metadata"] = {}
        results.append(d)
    return results


def delete_session(session_id: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Deletes a session and associated reports."""
    init_db(db_path)
    conn = get_connection(db_path)
    with conn:
        cur = conn.execute("DELETE FROM sessions WHERE session_id = ?;", (session_id,))
        return cur.rowcount > 0


def save_report(
    report_id: str,
    session_id: str,
    topic: str,
    content: str,
    score: float = 0.0,
    verifier_feedback: str = "",
    mindmap: Optional[dict] = None,
    db_path: str = DEFAULT_DB_PATH
) -> dict:
    """Inserts or updates a report in the database."""
    import datetime
    import json
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    mm_json = json.dumps(mindmap or {})
    
    # Ensure session exists
    if not get_session(session_id, db_path=db_path):
        save_session(session_id=session_id, title=topic, summary=content[:200], db_path=db_path)
        
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO reports (report_id, session_id, topic, content, score, verifier_feedback, mindmap, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_id) DO UPDATE SET
                session_id=excluded.session_id,
                topic=excluded.topic,
                content=excluded.content,
                score=excluded.score,
                verifier_feedback=excluded.verifier_feedback,
                mindmap=excluded.mindmap,
                created_at=excluded.created_at;
        """, (report_id, session_id, topic, content, score, verifier_feedback, mm_json, now_iso))
        
    return get_report(report_id, db_path=db_path)


def get_report(report_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    """Retrieves a report by ID."""
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reports WHERE report_id = ?;", (report_id,))
    row = cursor.fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        data["mindmap"] = json.loads(data.get("mindmap") or "{}")
    except Exception:
        data["mindmap"] = {}
    return data


def list_reports(session_id: Optional[str] = None, limit: Optional[int] = None, db_path: str = DEFAULT_DB_PATH) -> list:
    """Lists reports, optionally filtered by session_id and limited by count."""
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    query = "SELECT * FROM reports"
    params = []
    if session_id:
        query += " WHERE session_id = ?"
        params.append(session_id)
    query += " ORDER BY created_at DESC"
    if limit is not None and limit > 0:
        query += " LIMIT ?"
        params.append(limit)
    cursor.execute(query + ";", params)
    rows = cursor.fetchall()
    results = []
    for r in rows:
        d = dict(r)
        try:
            d["mindmap"] = json.loads(d.get("mindmap") or "{}")
        except Exception:
            d["mindmap"] = {}
        results.append(d)
    return results


def get_latest_report(session_id: Optional[str] = None, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    """Retrieves the most recent report."""
    reps = list_reports(session_id=session_id, db_path=db_path)
    return reps[0] if reps else None
