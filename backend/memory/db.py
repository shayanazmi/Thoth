import os
import sqlite3
from typing import Optional, Tuple, List, Dict, Any

_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DB_CANDIDATE = os.path.join(_ROOT_DIR, "db", "store.db")
DEFAULT_DB_PATH = _DB_CANDIDATE if os.path.exists(_DB_CANDIDATE) else os.path.join(_ROOT_DIR, "store.db")

def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                note_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                created TEXT NOT NULL,
                confidence REAL DEFAULT 1.0
            );
        """)

        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                note_id UNINDEXED,
                body
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                note_id TEXT PRIMARY KEY,
                vector BLOB NOT NULL,
                dim INTEGER NOT NULL
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                source_note TEXT NOT NULL,
                relation TEXT NOT NULL CHECK (relation IN ('cites', 'supports', 'contradicts', 'part_of', 'defines', 'related')),
                target_note TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                PRIMARY KEY (source_note, relation, target_note)
            );
        """)

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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS http_cache (
                cache_key TEXT PRIMARY KEY,
                response_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ttl_seconds INTEGER DEFAULT 86400
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS research_briefs (
                brief_id TEXT PRIMARY KEY,
                session_id TEXT DEFAULT '',
                topic TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                research_question TEXT NOT NULL,
                objectives_json TEXT NOT NULL DEFAULT '[]',
                hypotheses_json TEXT NOT NULL DEFAULT '[]',
                assumptions_json TEXT NOT NULL DEFAULT '[]',
                search_scope TEXT NOT NULL DEFAULT '',
                selection_criteria_json TEXT NOT NULL DEFAULT '[]',
                thinker_context_json TEXT NOT NULL DEFAULT '{}',
                unresolved_questions_json TEXT NOT NULL DEFAULT '[]',
                approval_status TEXT NOT NULL DEFAULT 'PENDING_APPROVAL',
                approved_version INTEGER,
                approved_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS research_tasks (
                task_id TEXT PRIMARY KEY,
                brief_id TEXT NOT NULL,
                brief_version INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', 'FAILED_ORPHANED')),
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL,
                error_code TEXT,
                error_summary TEXT,
                worker_id TEXT,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (brief_id) REFERENCES research_briefs(brief_id) ON DELETE CASCADE
            );
        """)

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_active_research_task 
            ON research_tasks(brief_id, brief_version) 
            WHERE status IN ('QUEUED', 'RUNNING');
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_brief ON research_tasks(brief_id);
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON research_tasks(status);
        """)

    return conn

def save_session(
    session_id: str,
    title: str,
    summary: str = "",
    metadata: Optional[dict] = None,
    db_path: str = DEFAULT_DB_PATH
) -> dict:
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
    import datetime
    import json
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    mm_json = json.dumps(mindmap or {})

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
    reps = list_reports(session_id=session_id, db_path=db_path)
    return reps[0] if reps else None

def get_cached_response(cache_key: str, db_path: str = DEFAULT_DB_PATH) -> Optional[str]:
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT response_json, created_at, ttl_seconds FROM http_cache WHERE cache_key = ?;
        """, (cache_key,))
        row = cursor.fetchone()
        if not row:
            return None
        return row["response_json"]
    except Exception:
        return None

def set_cached_response(cache_key: str, response_json: str, ttl_seconds: int = 86400, db_path: str = DEFAULT_DB_PATH):
    try:
        init_db(db_path)
        conn = get_connection(db_path)
        with conn:
            conn.execute("""
                INSERT INTO http_cache (cache_key, response_json, ttl_seconds)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    response_json = excluded.response_json,
                    created_at = CURRENT_TIMESTAMP,
                    ttl_seconds = excluded.ttl_seconds;
            """, (cache_key, response_json, ttl_seconds))
    except Exception:
        pass


def save_brief_db(brief_data: dict, db_path: str = DEFAULT_DB_PATH) -> dict:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO research_briefs (
                brief_id, session_id, topic, version, research_question,
                objectives_json, hypotheses_json, assumptions_json, search_scope,
                selection_criteria_json, thinker_context_json, unresolved_questions_json,
                approval_status, approved_version, approved_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(brief_id) DO UPDATE SET
                session_id=excluded.session_id,
                topic=excluded.topic,
                version=excluded.version,
                research_question=excluded.research_question,
                objectives_json=excluded.objectives_json,
                hypotheses_json=excluded.hypotheses_json,
                assumptions_json=excluded.assumptions_json,
                search_scope=excluded.search_scope,
                selection_criteria_json=excluded.selection_criteria_json,
                thinker_context_json=excluded.thinker_context_json,
                unresolved_questions_json=excluded.unresolved_questions_json,
                approval_status=excluded.approval_status,
                approved_version=excluded.approved_version,
                approved_at=excluded.approved_at,
                updated_at=excluded.updated_at;
        """, (
            brief_data["brief_id"],
            brief_data.get("session_id", ""),
            brief_data["topic"],
            brief_data.get("version", 1),
            brief_data["research_question"],
            json.dumps(brief_data.get("objectives", [])),
            json.dumps(brief_data.get("hypotheses", [])),
            json.dumps(brief_data.get("context_and_assumptions", [])),
            brief_data.get("search_scope", ""),
            json.dumps(brief_data.get("selection_criteria", [])),
            json.dumps(brief_data.get("thinker_context") or {}),
            json.dumps(brief_data.get("unresolved_questions", [])),
            brief_data.get("approval_status", "PENDING_APPROVAL"),
            brief_data.get("approved_version"),
            brief_data.get("approved_at"),
            brief_data.get("created_at"),
            brief_data.get("updated_at"),
        ))
    return get_brief_db(brief_data["brief_id"], db_path=db_path)


def get_brief_db(brief_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM research_briefs WHERE brief_id = ?;", (brief_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    d["objectives"] = json.loads(d.get("objectives_json") or "[]")
    d["hypotheses"] = json.loads(d.get("hypotheses_json") or "[]")
    d["context_and_assumptions"] = json.loads(d.get("assumptions_json") or "[]")
    d["selection_criteria"] = json.loads(d.get("selection_criteria_json") or "[]")
    d["thinker_context"] = json.loads(d.get("thinker_context_json") or "{}") or None
    d["unresolved_questions"] = json.loads(d.get("unresolved_questions_json") or "[]")
    return d


def list_briefs_db(session_id: Optional[str] = None, limit: int = 50, db_path: str = DEFAULT_DB_PATH) -> list:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    if session_id:
        cursor.execute("SELECT * FROM research_briefs WHERE session_id = ? ORDER BY updated_at DESC LIMIT ?;", (session_id, limit))
    else:
        cursor.execute("SELECT * FROM research_briefs ORDER BY updated_at DESC LIMIT ?;", (limit,))
    rows = cursor.fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["objectives"] = json.loads(d.get("objectives_json") or "[]")
        d["hypotheses"] = json.loads(d.get("hypotheses_json") or "[]")
        d["context_and_assumptions"] = json.loads(d.get("assumptions_json") or "[]")
        d["selection_criteria"] = json.loads(d.get("selection_criteria_json") or "[]")
        d["thinker_context"] = json.loads(d.get("thinker_context_json") or "{}") or None
        d["unresolved_questions"] = json.loads(d.get("unresolved_questions_json") or "[]")
        results.append(d)
    return results


def save_task_db(task_data: dict, db_path: str = DEFAULT_DB_PATH) -> dict:
    import datetime
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO research_tasks (
                task_id, brief_id, brief_version, status,
                created_at, started_at, completed_at, updated_at,
                error_code, error_summary, worker_id, cancel_requested
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                brief_id=excluded.brief_id,
                brief_version=excluded.brief_version,
                status=excluded.status,
                started_at=excluded.started_at,
                completed_at=excluded.completed_at,
                updated_at=excluded.updated_at,
                error_code=excluded.error_code,
                error_summary=excluded.error_summary,
                worker_id=excluded.worker_id,
                cancel_requested=excluded.cancel_requested;
        """, (
            task_data["task_id"],
            task_data["brief_id"],
            task_data.get("brief_version", 1),
            task_data.get("status", "QUEUED"),
            task_data.get("created_at", now_iso),
            task_data.get("started_at"),
            task_data.get("completed_at"),
            task_data.get("updated_at", now_iso),
            task_data.get("error_code"),
            task_data.get("error_summary"),
            task_data.get("worker_id"),
            1 if task_data.get("cancel_requested") else 0,
        ))
    return get_task_db(task_data["task_id"], db_path=db_path)


def get_task_db(task_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM research_tasks WHERE task_id = ?;", (task_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def get_active_task_for_brief_db(
    brief_id: str,
    brief_version: Optional[int] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[dict]:
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    if brief_version is not None:
        cursor.execute(
            "SELECT * FROM research_tasks WHERE brief_id = ? AND brief_version = ? AND status IN ('QUEUED', 'RUNNING') ORDER BY created_at DESC LIMIT 1;",
            (brief_id, brief_version)
        )
    else:
        cursor.execute(
            "SELECT * FROM research_tasks WHERE brief_id = ? AND status IN ('QUEUED', 'RUNNING') ORDER BY created_at DESC LIMIT 1;",
            (brief_id,)
        )
    row = cursor.fetchone()
    return dict(row) if row else None


def get_completed_task_for_brief_db(
    brief_id: str,
    brief_version: int,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[dict]:
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM research_tasks WHERE brief_id = ? AND brief_version = ? AND status = 'COMPLETED' ORDER BY completed_at DESC LIMIT 1;",
        (brief_id, brief_version)
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def list_tasks_db(
    brief_id: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> list:
    db_path = db_path or DEFAULT_DB_PATH
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    if brief_id:
        cursor.execute(
            "SELECT * FROM research_tasks WHERE brief_id = ? ORDER BY created_at DESC LIMIT ?;",
            (brief_id, limit)
        )
    else:
        cursor.execute(
            "SELECT * FROM research_tasks ORDER BY created_at DESC LIMIT ?;",
            (limit,)
        )
    rows = cursor.fetchall()
    return [dict(r) for r in rows]


def create_task_atomic_db(
    task_id: str,
    brief_id: str,
    brief_version: int,
    worker_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> Tuple[bool, Optional[dict], str]:
    import datetime
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            # 1. Authoritative brief check in persistent DB
            cursor.execute(
                "SELECT brief_id, version, approval_status, approved_version FROM research_briefs WHERE brief_id = ?;",
                (brief_id,)
            )
            b_row = cursor.fetchone()
            if not b_row:
                return False, None, f"Research brief '{brief_id}' does not exist in database."
            b_dict = dict(b_row)
            if b_dict["approval_status"] != "APPROVED":
                return False, None, f"Approval Barrier: Brief '{brief_id}' is in state '{b_dict['approval_status']}'. Explicit user approval is required."
            if b_dict["version"] != brief_version or b_dict["approved_version"] != brief_version:
                return False, None, f"Version Mismatch: Task requested for v{brief_version}, but brief is at v{b_dict['version']} (approved v{b_dict['approved_version']})."

            # 2. Check for completed task
            cursor.execute(
                "SELECT task_id, status FROM research_tasks WHERE brief_id = ? AND brief_version = ? AND status = 'COMPLETED';",
                (brief_id, brief_version)
            )
            comp_row = cursor.fetchone()
            if comp_row:
                return False, dict(comp_row), f"Research task '{comp_row['task_id']}' has already completed for brief '{brief_id}' (version {brief_version}). Completed tasks cannot be re-run."

            # 3. Check for active task
            cursor.execute(
                "SELECT task_id, status FROM research_tasks WHERE brief_id = ? AND brief_version = ? AND status IN ('QUEUED', 'RUNNING');",
                (brief_id, brief_version)
            )
            act_row = cursor.fetchone()
            if act_row:
                return False, dict(act_row), f"A research task '{act_row['task_id']}' is already running or active ({act_row['status']}) for brief '{brief_id}' (version {brief_version})."

            # 4. Insert task in QUEUED status
            conn.execute("""
                INSERT INTO research_tasks (
                    task_id, brief_id, brief_version, status,
                    created_at, started_at, completed_at, updated_at,
                    error_code, error_summary, worker_id, cancel_requested
                )
                VALUES (?, ?, ?, 'QUEUED', ?, NULL, NULL, ?, NULL, NULL, ?, 0);
            """, (task_id, brief_id, brief_version, now_iso, now_iso, worker_id))

        task = get_task_db(task_id, db_path=db_path)
        return True, task, "Task registered."
    except sqlite3.IntegrityError as e:
        active = get_active_task_for_brief_db(brief_id, brief_version, db_path=db_path)
        if active:
            return False, active, f"A research task '{active['task_id']}' is already running for brief '{brief_id}'."
        return False, None, f"Database integrity error registering task: {e}"


def claim_task_atomic_db(
    task_id: str,
    worker_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Tuple[bool, Optional[dict], str]:
    import datetime
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM research_tasks WHERE task_id = ?;", (task_id,))
        t_row = cursor.fetchone()
        if not t_row:
            return False, None, f"Task '{task_id}' not found."

        task = dict(t_row)
        if task["status"] != "QUEUED":
            return False, task, f"Task '{task_id}' cannot be claimed: status is '{task['status']}'."

        if task.get("cancel_requested") == 1:
            conn.execute("""
                UPDATE research_tasks
                SET status = 'CANCELLED', completed_at = ?, updated_at = ?
                WHERE task_id = ?;
            """, (now_iso, now_iso, task_id))
            return False, get_task_db(task_id, db_path=db_path), f"Task '{task_id}' was cancelled before execution claim."

        # Revalidate brief status
        cursor.execute(
            "SELECT version, approval_status, approved_version FROM research_briefs WHERE brief_id = ?;",
            (task["brief_id"],)
        )
        b_row = cursor.fetchone()
        if not b_row:
            conn.execute("""
                UPDATE research_tasks
                SET status = 'FAILED', error_code = 'BRIEF_NOT_FOUND',
                    error_summary = 'Brief was deleted before execution claim.',
                    completed_at = ?, updated_at = ?
                WHERE task_id = ?;
            """, (now_iso, now_iso, task_id))
            return False, get_task_db(task_id, db_path=db_path), "Brief not found at claim boundary."

        b_data = dict(b_row)
        if (b_data["approval_status"] != "APPROVED" or
            b_data["version"] != task["brief_version"] or
            b_data["approved_version"] != task["brief_version"]):
            conn.execute("""
                UPDATE research_tasks
                SET status = 'FAILED', error_code = 'APPROVAL_REVOKED',
                    error_summary = 'Brief approval was modified or revoked before execution started.',
                    completed_at = ?, updated_at = ?
                WHERE task_id = ?;
            """, (now_iso, now_iso, task_id))
            return False, get_task_db(task_id, db_path=db_path), "Authorization revoked or modified before execution claim."

        cursor.execute("""
            UPDATE research_tasks
            SET status = 'RUNNING', started_at = ?, updated_at = ?, worker_id = ?
            WHERE task_id = ? AND status = 'QUEUED';
        """, (now_iso, now_iso, worker_id, task_id))

        if cursor.rowcount == 0:
            return False, get_task_db(task_id, db_path=db_path), "Task claim conflict: another worker claimed the task."

    return True, get_task_db(task_id, db_path=db_path), "Task claimed successfully."


def update_task_status_db(
    task_id: str,
    status: str,
    error_code: Optional[str] = None,
    error_summary: Optional[str] = None,
    expected_status: Optional[str] = None,
    db_path: Optional[str] = None,
) -> bool:
    db_path = db_path or DEFAULT_DB_PATH
    import datetime
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM research_tasks WHERE task_id = ?;", (task_id,))
        row = cursor.fetchone()
        if not row:
            return False
        if row["status"] == "CANCELLED":
            # Late updates cannot overwrite CANCELLED
            return False
        if expected_status is not None and row["status"] != expected_status:
            return False
        # Prevent regression from terminal state to active state
        if row["status"] in ("COMPLETED", "FAILED", "CANCELLED", "FAILED_ORPHANED") and status in ("QUEUED", "RUNNING"):
            return False

        if status in ("COMPLETED", "FAILED", "CANCELLED", "FAILED_ORPHANED"):
            cursor.execute("""
                UPDATE research_tasks
                SET status = ?, completed_at = ?, updated_at = ?, error_code = ?, error_summary = ?
                WHERE task_id = ? AND status != 'CANCELLED';
            """, (status, now_iso, now_iso, error_code, error_summary, task_id))
        else:
            cursor.execute("""
                UPDATE research_tasks
                SET status = ?, updated_at = ?, error_code = ?, error_summary = ?
                WHERE task_id = ? AND status != 'CANCELLED';
            """, (status, now_iso, error_code, error_summary, task_id))
        return cursor.rowcount > 0


def request_task_cancellation_db(
    identifier: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Tuple[bool, list]:
    import datetime
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    affected_ids = []
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT task_id, status FROM research_tasks
            WHERE (task_id = ? OR brief_id = ?) AND status IN ('QUEUED', 'RUNNING');
        """, (identifier, identifier))
        rows = cursor.fetchall()
        for r in rows:
            tid = r["task_id"]
            affected_ids.append(tid)
            if r["status"] == "QUEUED":
                conn.execute("""
                    UPDATE research_tasks
                    SET status = 'CANCELLED', cancel_requested = 1, completed_at = ?, updated_at = ?
                    WHERE task_id = ?;
                """, (now_iso, now_iso, tid))
            else:
                conn.execute("""
                    UPDATE research_tasks
                    SET cancel_requested = 1, updated_at = ?
                    WHERE task_id = ?;
                """, (now_iso, tid))
    return len(affected_ids) > 0, affected_ids


def reconcile_orphaned_tasks_db(
    worker_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    import datetime
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        if worker_id:
            cursor.execute("""
                UPDATE research_tasks
                SET status = 'FAILED_ORPHANED', completed_at = ?, updated_at = ?,
                    error_code = 'PROCESS_RESTARTED',
                    error_summary = 'Process terminated while task was active (server restart/crash recovery).'
                WHERE status IN ('QUEUED', 'RUNNING') AND worker_id = ?;
            """, (now_iso, now_iso, worker_id))
        else:
            cursor.execute("""
                UPDATE research_tasks
                SET status = 'FAILED_ORPHANED', completed_at = ?, updated_at = ?,
                    error_code = 'PROCESS_RESTARTED',
                    error_summary = 'Process terminated while task was active (server restart/crash recovery).'
                WHERE status IN ('QUEUED', 'RUNNING');
            """, (now_iso, now_iso))
        return cursor.rowcount


def clear_tasks_db(db_path: str = DEFAULT_DB_PATH):
    init_db(db_path)
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM research_tasks;")
