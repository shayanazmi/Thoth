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
                updated_at TEXT NOT NULL,
                idea_id TEXT DEFAULT NULL,
                counter_evidence_queries_json TEXT NOT NULL DEFAULT '[]',
                falsification_criteria_json TEXT NOT NULL DEFAULT '[]'
            );
        """)

        try:
            conn.execute("ALTER TABLE research_briefs ADD COLUMN idea_id TEXT DEFAULT NULL;")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE research_briefs ADD COLUMN counter_evidence_queries_json TEXT NOT NULL DEFAULT '[]';")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE research_briefs ADD COLUMN falsification_criteria_json TEXT NOT NULL DEFAULT '[]';")
        except sqlite3.OperationalError:
            pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS research_ideas (
                idea_id TEXT PRIMARY KEY,
                session_id TEXT DEFAULT '',
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                hypothesis TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('TENTATIVE', 'PROMOTED', 'REVISED', 'ABANDONED')),
                thinker_id TEXT DEFAULT '',
                thinker_critique TEXT DEFAULT '',
                unresolved_objections_json TEXT NOT NULL DEFAULT '[]',
                parent_idea_id TEXT DEFAULT NULL,
                revision_version INTEGER NOT NULL DEFAULT 1,
                revision_notes TEXT DEFAULT '',
                brief_id TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (parent_idea_id) REFERENCES research_ideas(idea_id) ON DELETE SET NULL,
                FOREIGN KEY (brief_id) REFERENCES research_briefs(brief_id) ON DELETE SET NULL
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ideas_session ON research_ideas(session_id);
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ideas_parent ON research_ideas(parent_idea_id);
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ideas_brief ON research_ideas(brief_id);
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ideas_status ON research_ideas(status);
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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS prisma_reviews (
                review_id TEXT PRIMARY KEY,
                brief_id TEXT NOT NULL,
                session_id TEXT DEFAULT '',
                topic TEXT NOT NULL,
                protocol_json TEXT NOT NULL DEFAULT '{}',
                flow_counts_json TEXT NOT NULL DEFAULT '{}',
                evidence_matrix_json TEXT NOT NULL DEFAULT '{}',
                mermaid_diagram TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (brief_id) REFERENCES research_briefs(brief_id) ON DELETE CASCADE
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_prisma_brief ON prisma_reviews(brief_id);
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_prisma_session ON prisma_reviews(session_id);
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS screening_decisions (
                decision_id TEXT PRIMARY KEY,
                review_id TEXT NOT NULL,
                brief_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_url TEXT DEFAULT '',
                title TEXT NOT NULL,
                stage TEXT NOT NULL CHECK (stage IN ('TITLE_ABSTRACT', 'FULL_TEXT_ELIGIBILITY')),
                disposition TEXT NOT NULL CHECK (disposition IN ('INCLUDED', 'EXCLUDED', 'UNRESOLVED', 'NOT_RETRIEVED')),
                criteria_applied_json TEXT NOT NULL DEFAULT '[]',
                exclusion_reason TEXT DEFAULT '',
                rationale TEXT DEFAULT '',
                supporting_passages_json TEXT NOT NULL DEFAULT '[]',
                reviewer_type TEXT NOT NULL DEFAULT 'AI_RECOMMENDED' CHECK (reviewer_type IN ('AI_RECOMMENDED', 'REVIEWER_CONFIRMED')),
                study_id TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (review_id) REFERENCES prisma_reviews(review_id) ON DELETE CASCADE
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_screening_review ON screening_decisions(review_id);
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_screening_brief ON screening_decisions(brief_id);
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_screening_stage_disp ON screening_decisions(stage, disposition);
        """)

        # Phase 5: Projects, Manuscripts, Revisions, Claims, and Exports
        conn.execute("""
            CREATE TABLE IF NOT EXISTS research_projects (
                project_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                session_id TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED', 'COMPLETED')),
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_projects_session ON research_projects(session_id);
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON research_projects(updated_at DESC);
        """)

        # Add project_id columns to existing entities if not present
        for tbl in ["research_briefs", "research_ideas", "prisma_reviews", "reports"]:
            try:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN project_id TEXT DEFAULT NULL;")
            except sqlite3.OperationalError:
                pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS manuscripts (
                manuscript_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                current_version INTEGER NOT NULL DEFAULT 1,
                brief_id TEXT DEFAULT NULL,
                review_id TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES research_projects(project_id) ON DELETE CASCADE
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_manuscripts_project ON manuscripts(project_id);
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS manuscript_revisions (
                revision_id TEXT PRIMARY KEY,
                manuscript_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                title TEXT NOT NULL,
                author_notes TEXT DEFAULT '',
                sections_json TEXT NOT NULL DEFAULT '{}',
                claims_json TEXT NOT NULL DEFAULT '[]',
                references_json TEXT NOT NULL DEFAULT '[]',
                evidence_matrix_json TEXT NOT NULL DEFAULT '{}',
                diff_summary_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (manuscript_id) REFERENCES manuscripts(manuscript_id) ON DELETE CASCADE,
                UNIQUE (manuscript_id, version)
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_revisions_manuscript ON manuscript_revisions(manuscript_id);
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS manuscript_claims (
                claim_id TEXT PRIMARY KEY,
                manuscript_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                section TEXT NOT NULL,
                claim_text TEXT NOT NULL,
                evidence_status TEXT NOT NULL DEFAULT 'UNVERIFIED' CHECK (evidence_status IN ('SUPPORTED', 'QUALIFIED', 'CHALLENGED', 'UNVERIFIED')),
                supporting_sources_json TEXT NOT NULL DEFAULT '[]',
                counter_sources_json TEXT NOT NULL DEFAULT '[]',
                confidence REAL DEFAULT 0.0,
                reasoning TEXT DEFAULT '',
                uncertainties TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (manuscript_id) REFERENCES manuscripts(manuscript_id) ON DELETE CASCADE
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_claims_manuscript ON manuscript_claims(manuscript_id);
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS manuscript_exports (
                export_id TEXT PRIMARY KEY,
                manuscript_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                format TEXT NOT NULL CHECK (format IN ('markdown', 'latex', 'bibtex', 'html', 'pdf')),
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (manuscript_id) REFERENCES manuscripts(manuscript_id) ON DELETE CASCADE
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_exports_manuscript_version ON manuscript_exports(manuscript_id, version, format);
        """)

        # Migration helper for existing manuscript_exports table if created without 'pdf'
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='manuscript_exports';")
            row = cursor.fetchone()
            if row and row[0] and "'pdf'" not in row[0]:
                conn.execute("ALTER TABLE manuscript_exports RENAME TO manuscript_exports_old;")
                conn.execute("""
                    CREATE TABLE manuscript_exports (
                        export_id TEXT PRIMARY KEY,
                        manuscript_id TEXT NOT NULL,
                        version INTEGER NOT NULL,
                        format TEXT NOT NULL CHECK (format IN ('markdown', 'latex', 'bibtex', 'html', 'pdf')),
                        content TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (manuscript_id) REFERENCES manuscripts(manuscript_id) ON DELETE CASCADE
                    );
                """)
                conn.execute("INSERT INTO manuscript_exports SELECT * FROM manuscript_exports_old;")
                conn.execute("DROP TABLE manuscript_exports_old;")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_exports_manuscript_version ON manuscript_exports(manuscript_id, version, format);")
        except Exception:
            pass

        # Phase 6: Collaboration, Project Members, and Outbox Sync
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_members (
                membership_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('OWNER', 'EDITOR', 'VIEWER')),
                invited_at TEXT NOT NULL,
                accepted_at TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES research_projects(project_id) ON DELETE CASCADE,
                UNIQUE(project_id, user_id)
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_members_project ON project_members(project_id);
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_members_user ON project_members(user_id);
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_outbox (
                event_id TEXT PRIMARY KEY,
                project_id TEXT DEFAULT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                operation TEXT NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
                payload_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SYNCED', 'FAILED', 'CONFLICT')),
                retry_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                synced_at TEXT DEFAULT NULL
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_outbox_status ON sync_outbox(status);
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_outbox_project ON sync_outbox(project_id);
        """)

        # Phase 6: Recursive Citation Snowball Runs & Candidates
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snowball_runs (
                run_id TEXT PRIMARY KEY,
                review_id TEXT DEFAULT NULL,
                brief_id TEXT DEFAULT NULL,
                config_json TEXT NOT NULL DEFAULT '{}',
                stopping_reason TEXT NOT NULL,
                total_rounds INTEGER NOT NULL DEFAULT 0,
                total_candidates INTEGER NOT NULL DEFAULT 0,
                unique_candidates INTEGER NOT NULL DEFAULT 0,
                rounds_summary_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                FOREIGN KEY (review_id) REFERENCES prisma_reviews(review_id) ON DELETE CASCADE
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snowball_review ON snowball_runs(review_id);
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS snowball_candidates (
                candidate_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                review_id TEXT DEFAULT NULL,
                parent_paper_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                title TEXT NOT NULL,
                doi TEXT DEFAULT '',
                direction TEXT NOT NULL CHECK (direction IN ('BACKWARD', 'FORWARD')),
                round_number INTEGER NOT NULL,
                provider TEXT NOT NULL,
                lookup_params_json TEXT NOT NULL DEFAULT '{}',
                is_duplicate BOOLEAN NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES snowball_runs(run_id) ON DELETE CASCADE
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snowball_candidates_run ON snowball_candidates(run_id);
        """)

        # Phase 7: Deep Semantic Literature Clustering & Citation Network Graph
        conn.execute("""
            CREATE TABLE IF NOT EXISTS literature_clusters (
                cluster_run_id TEXT PRIMARY KEY,
                review_id TEXT NOT NULL,
                project_id TEXT DEFAULT NULL,
                algorithm TEXT NOT NULL DEFAULT 'TFIDF_KMEANS',
                num_clusters INTEGER NOT NULL DEFAULT 0,
                clusters_json TEXT NOT NULL DEFAULT '[]',
                summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (review_id) REFERENCES prisma_reviews(review_id) ON DELETE CASCADE
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_clusters_review ON literature_clusters(review_id);
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS citation_graphs (
                graph_id TEXT PRIMARY KEY,
                review_id TEXT NOT NULL,
                project_id TEXT DEFAULT NULL,
                nodes_json TEXT NOT NULL DEFAULT '[]',
                edges_json TEXT NOT NULL DEFAULT '[]',
                bridge_papers_json TEXT NOT NULL DEFAULT '[]',
                structural_holes_json TEXT NOT NULL DEFAULT '[]',
                metrics_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (review_id) REFERENCES prisma_reviews(review_id) ON DELETE CASCADE
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_graphs_review ON citation_graphs(review_id);
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS journal_submissions (
                submission_id TEXT PRIMARY KEY,
                manuscript_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                preset TEXT NOT NULL,
                is_anonymized BOOLEAN NOT NULL DEFAULT 0,
                package_filename TEXT NOT NULL,
                manifest_json TEXT NOT NULL DEFAULT '{}',
                checklist_md TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (manuscript_id) REFERENCES manuscripts(manuscript_id) ON DELETE CASCADE
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_submissions_manuscript ON journal_submissions(manuscript_id);
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
    import datetime
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    created_at = brief_data.get("created_at") or now_iso
    updated_at = brief_data.get("updated_at") or now_iso
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO research_briefs (
                brief_id, session_id, topic, version, research_question,
                objectives_json, hypotheses_json, assumptions_json, search_scope,
                selection_criteria_json, thinker_context_json, unresolved_questions_json,
                approval_status, approved_version, approved_at, created_at, updated_at, idea_id,
                counter_evidence_queries_json, falsification_criteria_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                updated_at=excluded.updated_at,
                idea_id=COALESCE(excluded.idea_id, research_briefs.idea_id),
                counter_evidence_queries_json=excluded.counter_evidence_queries_json,
                falsification_criteria_json=excluded.falsification_criteria_json;
        """, (
            brief_data["brief_id"],
            brief_data.get("session_id", ""),
            brief_data["topic"],
            brief_data.get("version", 1),
            brief_data.get("research_question", ""),
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
            created_at,
            updated_at,
            brief_data.get("idea_id"),
            json.dumps(brief_data.get("counter_evidence_queries", [])),
            json.dumps(brief_data.get("falsification_criteria", [])),
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
    d["idea_id"] = d.get("idea_id")
    d["counter_evidence_queries"] = json.loads(d.get("counter_evidence_queries_json") or "[]")
    d["falsification_criteria"] = json.loads(d.get("falsification_criteria_json") or "[]")
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
        d["idea_id"] = d.get("idea_id")
        d["counter_evidence_queries"] = json.loads(d.get("counter_evidence_queries_json") or "[]")
        d["falsification_criteria"] = json.loads(d.get("falsification_criteria_json") or "[]")
        results.append(d)
    return results


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


def get_idea_history_db(idea_id: str, db_path: str = DEFAULT_DB_PATH) -> list:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM research_ideas WHERE idea_id = ?;", (idea_id,))
    row = cursor.fetchone()
    if not row:
        return []

    curr = dict(row)
    root_id = curr["idea_id"]
    visited_ancestors = {root_id}
    while curr.get("parent_idea_id"):
        parent_id = curr["parent_idea_id"]
        if parent_id in visited_ancestors:
            break
        visited_ancestors.add(parent_id)
        cursor.execute("SELECT * FROM research_ideas WHERE idea_id = ?;", (parent_id,))
        p_row = cursor.fetchone()
        if not p_row:
            break
        curr = dict(p_row)
        root_id = curr["idea_id"]

    family_ids = [root_id]
    to_visit = [root_id]
    seen = {root_id}
    while to_visit:
        pid = to_visit.pop(0)
        cursor.execute("SELECT idea_id FROM research_ideas WHERE parent_idea_id = ? ORDER BY revision_version ASC, created_at ASC;", (pid,))
        children = cursor.fetchall()
        for ch in children:
            cid = ch["idea_id"]
            if cid not in seen:
                seen.add(cid)
                family_ids.append(cid)
                to_visit.append(cid)

    placeholders = ",".join("?" for _ in family_ids)
    cursor.execute(f"SELECT * FROM research_ideas WHERE idea_id IN ({placeholders}) ORDER BY revision_version ASC, created_at ASC;", family_ids)
    rows = cursor.fetchall()
    history = []
    for r in rows:
        d = dict(r)
        d["unresolved_objections"] = json.loads(d.get("unresolved_objections_json") or "[]")
        history.append(d)
    return history


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


def save_prisma_review_db(
    review_data: Dict[str, Any],
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    import json
    import datetime
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    rev_id = review_data.get("review_id") or f"rev-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    brief_id = review_data.get("brief_id") or ""
    session_id = review_data.get("session_id") or ""
    topic = review_data.get("topic") or ""

    protocol_json = json.dumps(review_data.get("protocol") or {})
    flow_counts_json = json.dumps(review_data.get("flow_counts") or {})
    evidence_matrix_json = json.dumps(review_data.get("evidence_matrix") or {})
    mermaid_diagram = review_data.get("mermaid_diagram") or ""
    created_at = review_data.get("created_at") or now_iso
    updated_at = now_iso

    conn = get_connection(db_path)
    with conn:
        if brief_id:
            conn.execute("""
                INSERT OR IGNORE INTO research_briefs (
                    brief_id, session_id, topic, research_question, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?);
            """, (brief_id, session_id, topic or "Systematic Review", f"Review for {topic or brief_id}", created_at, updated_at))

        conn.execute("""
            INSERT INTO prisma_reviews (
                review_id, brief_id, session_id, topic, protocol_json,
                flow_counts_json, evidence_matrix_json, mermaid_diagram,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(review_id) DO UPDATE SET
                protocol_json=excluded.protocol_json,
                flow_counts_json=excluded.flow_counts_json,
                evidence_matrix_json=excluded.evidence_matrix_json,
                mermaid_diagram=excluded.mermaid_diagram,
                updated_at=excluded.updated_at;
        """, (
            rev_id, brief_id, session_id, topic, protocol_json,
            flow_counts_json, evidence_matrix_json, mermaid_diagram,
            created_at, updated_at
        ))
    return get_prisma_review_db(rev_id, db_path=db_path) or review_data


def get_prisma_review_db(
    review_id_or_brief_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM prisma_reviews
        WHERE review_id = ? OR brief_id = ?
        ORDER BY updated_at DESC LIMIT 1;
    """, (review_id_or_brief_id, review_id_or_brief_id))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["protocol"] = json.loads(d.get("protocol_json") or "{}")
    except Exception:
        d["protocol"] = {}
    try:
        d["flow_counts"] = json.loads(d.get("flow_counts_json") or "{}")
    except Exception:
        d["flow_counts"] = {}
    try:
        d["evidence_matrix"] = json.loads(d.get("evidence_matrix_json") or "{}")
    except Exception:
        d["evidence_matrix"] = {}
    return d


def list_prisma_reviews_db(
    session_id: Optional[str] = None,
    limit: Optional[int] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    query = "SELECT * FROM prisma_reviews"
    params = []
    if session_id:
        query += " WHERE session_id = ?"
        params.append(session_id)
    query += " ORDER BY created_at DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    query += ";"
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["protocol"] = json.loads(d.get("protocol_json") or "{}")
        except Exception:
            d["protocol"] = {}
        try:
            d["flow_counts"] = json.loads(d.get("flow_counts_json") or "{}")
        except Exception:
            d["flow_counts"] = {}
        try:
            d["evidence_matrix"] = json.loads(d.get("evidence_matrix_json") or "{}")
        except Exception:
            d["evidence_matrix"] = {}
        out.append(d)
    return out


def save_screening_decision_db(
    decision_data: Dict[str, Any],
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    import json
    import datetime
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    dec_id = decision_data.get("decision_id") or f"dec-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    review_id = decision_data.get("review_id") or ""
    brief_id = decision_data.get("brief_id") or ""
    source_id = decision_data.get("source_id") or ""
    source_url = decision_data.get("source_url") or ""
    title = decision_data.get("title") or "Untitled"
    stage = decision_data.get("stage") or "TITLE_ABSTRACT"
    disposition = decision_data.get("disposition") or "INCLUDED"
    criteria_json = json.dumps(decision_data.get("criteria_applied") or [])
    exclusion_reason = decision_data.get("exclusion_reason") or ""
    rationale = decision_data.get("rationale") or ""
    passages_json = json.dumps(decision_data.get("supporting_passages") or [])
    reviewer_type = decision_data.get("reviewer_type") or "AI_RECOMMENDED"
    study_id = decision_data.get("study_id") or ""
    created_at = decision_data.get("created_at") or now_iso
    updated_at = now_iso

    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO screening_decisions (
                decision_id, review_id, brief_id, source_id, source_url, title,
                stage, disposition, criteria_applied_json, exclusion_reason,
                rationale, supporting_passages_json, reviewer_type, study_id,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(decision_id) DO UPDATE SET
                disposition=excluded.disposition,
                criteria_applied_json=excluded.criteria_applied_json,
                exclusion_reason=excluded.exclusion_reason,
                rationale=excluded.rationale,
                supporting_passages_json=excluded.supporting_passages_json,
                reviewer_type=excluded.reviewer_type,
                study_id=excluded.study_id,
                updated_at=excluded.updated_at;
        """, (
            dec_id, review_id, brief_id, source_id, source_url, title,
            stage, disposition, criteria_json, exclusion_reason,
            rationale, passages_json, reviewer_type, study_id,
            created_at, updated_at
        ))
    return get_screening_decision_db(dec_id, db_path=db_path) or decision_data


def get_screening_decision_db(
    decision_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM screening_decisions WHERE decision_id = ?;", (decision_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["criteria_applied"] = json.loads(d.get("criteria_applied_json") or "[]")
    except Exception:
        d["criteria_applied"] = []
    try:
        d["supporting_passages"] = json.loads(d.get("supporting_passages_json") or "[]")
    except Exception:
        d["supporting_passages"] = []
    return d


def list_screening_decisions_db(
    review_id: Optional[str] = None,
    brief_id: Optional[str] = None,
    stage: Optional[str] = None,
    disposition: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()

    query = "SELECT * FROM screening_decisions WHERE 1=1"
    params: List[Any] = []
    if review_id:
        query += " AND review_id = ?"
        params.append(review_id)
    if brief_id:
        query += " AND brief_id = ?"
        params.append(brief_id)
    if stage:
        query += " AND stage = ?"
        params.append(stage)
    if disposition:
        query += " AND disposition = ?"
        params.append(disposition)
    query += " ORDER BY created_at ASC;"

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["criteria_applied"] = json.loads(d.get("criteria_applied_json") or "[]")
        except Exception:
            d["criteria_applied"] = []
        try:
            d["supporting_passages"] = json.loads(d.get("supporting_passages_json") or "[]")
        except Exception:
            d["supporting_passages"] = []
        out.append(d)
    return out


def update_screening_decision_db(
    decision_id: str,
    disposition: str,
    reviewer_notes: str = "",
    reviewer_type: str = "REVIEWER_CONFIRMED",
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    import datetime
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT rationale FROM screening_decisions WHERE decision_id = ?;", (decision_id,))
        row = cursor.fetchone()
        if not row:
            return False
        old_rationale = row["rationale"] or ""
        new_rationale = f"{old_rationale} [Reviewer Note: {reviewer_notes}]" if reviewer_notes else old_rationale

        cursor.execute("""
            UPDATE screening_decisions
            SET disposition = ?, reviewer_type = ?, rationale = ?, updated_at = ?
            WHERE decision_id = ?;
        """, (disposition, reviewer_type, new_rationale, now_iso, decision_id))
        return cursor.rowcount > 0


# ==========================================
# Phase 5: Projects, Manuscripts, Revisions, Claims, Exports
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


def get_project_db(project_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM research_projects WHERE project_id = ?;", (project_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["metadata"] = json.loads(d.get("metadata_json") or "{}")
    except Exception:
        d["metadata"] = {}
    return d


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


def delete_project_db(project_id: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    init_db(db_path)
    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM research_projects WHERE project_id = ?;", (project_id,))
        return cursor.rowcount > 0


def associate_artifact_to_project_db(
    artifact_type: str,
    artifact_id: str,
    project_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    init_db(db_path)
    conn = get_connection(db_path)

    table_map = {
        "brief": ("research_briefs", "brief_id"),
        "idea": ("research_ideas", "idea_id"),
        "prisma_review": ("prisma_reviews", "review_id"),
        "report": ("reports", "report_id"),
    }

    if artifact_type not in table_map:
        raise ValueError(f"Unsupported artifact type '{artifact_type}' for project association.")

    tbl, id_col = table_map[artifact_type]

    with conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE {tbl} SET project_id = ? WHERE {id_col} = ?;", (project_id, artifact_id))
        return cursor.rowcount > 0


def save_manuscript_db(
    manuscript_id: str,
    project_id: str,
    title: str,
    current_version: int = 1,
    brief_id: Optional[str] = None,
    review_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    import datetime
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT created_at FROM manuscripts WHERE manuscript_id = ?;", (manuscript_id,))
        row = cursor.fetchone()
        created_at = row["created_at"] if row else now_iso

        cursor.execute("""
            INSERT INTO manuscripts (manuscript_id, project_id, title, current_version, brief_id, review_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(manuscript_id) DO UPDATE SET
                title = excluded.title,
                current_version = excluded.current_version,
                brief_id = excluded.brief_id,
                review_id = excluded.review_id,
                updated_at = excluded.updated_at;
        """, (manuscript_id, project_id, title, current_version, brief_id, review_id, created_at, now_iso))

    return {
        "manuscript_id": manuscript_id,
        "project_id": project_id,
        "title": title,
        "current_version": current_version,
        "brief_id": brief_id,
        "review_id": review_id,
        "created_at": created_at,
        "updated_at": now_iso,
    }


def get_manuscript_db(manuscript_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM manuscripts WHERE manuscript_id = ?;", (manuscript_id,))
    row = cursor.fetchone()
    if not row:
        return None
    return dict(row)


def list_manuscripts_db(project_id: Optional[str] = None, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    if project_id:
        cursor.execute("SELECT * FROM manuscripts WHERE project_id = ? ORDER BY updated_at DESC;", (project_id,))
    else:
        cursor.execute("SELECT * FROM manuscripts ORDER BY updated_at DESC;")
    return [dict(r) for r in cursor.fetchall()]


def save_manuscript_revision_db(
    revision_id: str,
    manuscript_id: str,
    version: int,
    title: str,
    author_notes: str = "",
    sections: Optional[dict] = None,
    claims: Optional[list] = None,
    references: Optional[list] = None,
    evidence_matrix: Optional[dict] = None,
    diff_summary: Optional[dict] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    import datetime
    import json
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    sections_json = json.dumps(sections or {})
    claims_json = json.dumps(claims or [])
    refs_json = json.dumps(references or [])
    ev_json = json.dumps(evidence_matrix or {})
    diff_json = json.dumps(diff_summary or {})

    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO manuscript_revisions (
                revision_id, manuscript_id, version, title, author_notes,
                sections_json, claims_json, references_json, evidence_matrix_json, diff_summary_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(manuscript_id, version) DO UPDATE SET
                title = excluded.title,
                author_notes = excluded.author_notes,
                sections_json = excluded.sections_json,
                claims_json = excluded.claims_json,
                references_json = excluded.references_json,
                evidence_matrix_json = excluded.evidence_matrix_json,
                diff_summary_json = excluded.diff_summary_json;
        """, (revision_id, manuscript_id, version, title, author_notes,
              sections_json, claims_json, refs_json, ev_json, diff_json, now_iso))

        # Update current_version on manuscript
        cursor.execute("""
            UPDATE manuscripts
            SET current_version = MAX(current_version, ?), updated_at = ?
            WHERE manuscript_id = ?;
        """, (version, now_iso, manuscript_id))

    return {
        "revision_id": revision_id,
        "manuscript_id": manuscript_id,
        "version": version,
        "title": title,
        "author_notes": author_notes,
        "sections": sections or {},
        "claims": claims or [],
        "references": references or [],
        "evidence_matrix": evidence_matrix or {},
        "diff_summary": diff_summary or {},
        "created_at": now_iso,
    }


def get_manuscript_revision_db(manuscript_id: str, version: int, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM manuscript_revisions WHERE manuscript_id = ? AND version = ?;
    """, (manuscript_id, version))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    for field, default in [
        ("sections_json", "{}"),
        ("claims_json", "[]"),
        ("references_json", "[]"),
        ("evidence_matrix_json", "{}"),
        ("diff_summary_json", "{}"),
    ]:
        key = field.replace("_json", "")
        try:
            d[key] = json.loads(d.get(field) or default)
        except Exception:
            d[key] = json.loads(default)
    return d


def list_manuscript_revisions_db(manuscript_id: str, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT revision_id, manuscript_id, version, title, author_notes, diff_summary_json, created_at
        FROM manuscript_revisions
        WHERE manuscript_id = ?
        ORDER BY version ASC;
    """, (manuscript_id,))
    rows = cursor.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["diff_summary"] = json.loads(d.get("diff_summary_json") or "{}")
        except Exception:
            d["diff_summary"] = {}
        out.append(d)
    return out


def save_manuscript_claim_db(
    claim_id: str,
    manuscript_id: str,
    revision_id: str,
    section: str,
    claim_text: str,
    evidence_status: str = "UNVERIFIED",
    supporting_sources: Optional[list] = None,
    counter_sources: Optional[list] = None,
    confidence: float = 0.0,
    reasoning: str = "",
    uncertainties: str = "",
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    import datetime
    import json
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    supp_json = json.dumps(supporting_sources or [])
    counter_json = json.dumps(counter_sources or [])

    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO manuscript_claims (
                claim_id, manuscript_id, revision_id, section, claim_text,
                evidence_status, supporting_sources_json, counter_sources_json,
                confidence, reasoning, uncertainties, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(claim_id) DO UPDATE SET
                revision_id = excluded.revision_id,
                section = excluded.section,
                claim_text = excluded.claim_text,
                evidence_status = excluded.evidence_status,
                supporting_sources_json = excluded.supporting_sources_json,
                counter_sources_json = excluded.counter_sources_json,
                confidence = excluded.confidence,
                reasoning = excluded.reasoning,
                uncertainties = excluded.uncertainties;
        """, (claim_id, manuscript_id, revision_id, section, claim_text,
              evidence_status, supp_json, counter_json, confidence, reasoning, uncertainties, now_iso))

    return {
        "claim_id": claim_id,
        "manuscript_id": manuscript_id,
        "revision_id": revision_id,
        "section": section,
        "claim_text": claim_text,
        "evidence_status": evidence_status,
        "supporting_sources": supporting_sources or [],
        "counter_sources": counter_sources or [],
        "confidence": confidence,
        "reasoning": reasoning,
        "uncertainties": uncertainties,
        "created_at": now_iso,
    }


def save_manuscript_claims_batch_db(claims: list[dict], db_path: str = DEFAULT_DB_PATH) -> bool:
    import datetime
    import json
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        for c in claims:
            supp_json = json.dumps(c.get("supporting_sources") or [])
            counter_json = json.dumps(c.get("counter_sources") or [])
            cursor.execute("""
                INSERT INTO manuscript_claims (
                    claim_id, manuscript_id, revision_id, section, claim_text,
                    evidence_status, supporting_sources_json, counter_sources_json,
                    confidence, reasoning, uncertainties, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(claim_id) DO UPDATE SET
                    revision_id = excluded.revision_id,
                    section = excluded.section,
                    claim_text = excluded.claim_text,
                    evidence_status = excluded.evidence_status,
                    supporting_sources_json = excluded.supporting_sources_json,
                    counter_sources_json = excluded.counter_sources_json,
                    confidence = excluded.confidence,
                    reasoning = excluded.reasoning,
                    uncertainties = excluded.uncertainties;
            """, (
                c["claim_id"], c["manuscript_id"], c.get("revision_id", ""), c.get("section", ""),
                c.get("claim_text", ""), c.get("evidence_status", "UNVERIFIED"),
                supp_json, counter_json, c.get("confidence", 0.0),
                c.get("reasoning", ""), c.get("uncertainties", ""), now_iso
            ))
        return True


def list_manuscript_claims_db(
    manuscript_id: str,
    revision_id: Optional[str] = None,
    section: Optional[str] = None,
    evidence_status: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()

    query = "SELECT * FROM manuscript_claims WHERE manuscript_id = ?"
    params = [manuscript_id]
    if revision_id:
        query += " AND revision_id = ?"
        params.append(revision_id)
    if section:
        query += " AND section = ?"
        params.append(section)
    if evidence_status:
        query += " AND evidence_status = ?"
        params.append(evidence_status)
    query += " ORDER BY created_at ASC;"

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["supporting_sources"] = json.loads(d.get("supporting_sources_json") or "[]")
        except Exception:
            d["supporting_sources"] = []
        try:
            d["counter_sources"] = json.loads(d.get("counter_sources_json") or "[]")
        except Exception:
            d["counter_sources"] = []
        out.append(d)
    return out


def save_manuscript_export_db(
    export_id: str,
    manuscript_id: str,
    version: int,
    format: str,
    content: str,
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
        cursor.execute("""
            INSERT INTO manuscript_exports (
                export_id, manuscript_id, version, format, content, metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(export_id) DO UPDATE SET
                content = excluded.content,
                metadata_json = excluded.metadata_json;
        """, (export_id, manuscript_id, version, format, content, meta_json, now_iso))

    return {
        "export_id": export_id,
        "manuscript_id": manuscript_id,
        "version": version,
        "format": format,
        "content": content,
        "metadata": metadata or {},
        "created_at": now_iso,
    }


def get_manuscript_export_db(export_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM manuscript_exports WHERE export_id = ?;", (export_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["metadata"] = json.loads(d.get("metadata_json") or "{}")
    except Exception:
        d["metadata"] = {}
    return d


def list_manuscript_exports_db(
    manuscript_id: str,
    version: Optional[int] = None,
    format: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()

    query = "SELECT * FROM manuscript_exports WHERE manuscript_id = ?"
    params = [manuscript_id]
    if version is not None:
        query += " AND version = ?"
        params.append(version)
    if format:
        query += " AND format = ?"
        params.append(format)
    query += " ORDER BY created_at DESC;"

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
# Phase 6: Project Memberships & Collaboration Persistence
# ==============================================================================

def add_project_member_db(
    membership_id: str,
    project_id: str,
    user_id: str,
    role: str,
    invited_at: Optional[str] = None,
    accepted_at: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    import datetime
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    inv_at = invited_at or now_iso

    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO project_members (
                membership_id, project_id, user_id, role, invited_at, accepted_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, user_id) DO UPDATE SET
                role = excluded.role,
                accepted_at = COALESCE(excluded.accepted_at, project_members.accepted_at);
        """, (membership_id, project_id, user_id, role, inv_at, accepted_at, now_iso))

    return get_project_member_db(project_id, user_id, db_path=db_path) or {
        "membership_id": membership_id,
        "project_id": project_id,
        "user_id": user_id,
        "role": role,
        "invited_at": inv_at,
        "accepted_at": accepted_at,
        "created_at": now_iso,
    }


def get_project_member_db(
    project_id: str,
    user_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[dict]:
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM project_members WHERE project_id = ? AND user_id = ?;",
        (project_id, user_id),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def list_project_members_db(
    project_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM project_members WHERE project_id = ? ORDER BY created_at ASC;",
        (project_id,),
    )
    return [dict(r) for r in cursor.fetchall()]


def delete_project_member_db(
    project_id: str,
    user_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    init_db(db_path)
    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM project_members WHERE project_id = ? AND user_id = ?;",
            (project_id, user_id),
        )
        return cursor.rowcount > 0


# ==============================================================================
# Phase 6: Sync Outbox Persistence
# ==============================================================================

def add_sync_outbox_event_db(
    event_id: str,
    entity_type: str,
    entity_id: str,
    operation: str,
    payload: dict,
    project_id: Optional[str] = None,
    status: str = "PENDING",
    error_message: str = "",
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    import datetime
    import json
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload_json = json.dumps(payload)

    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sync_outbox (
                event_id, project_id, entity_type, entity_id, operation,
                payload_json, status, retry_count, error_message, created_at, synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL);
        """, (event_id, project_id, entity_type, entity_id, operation, payload_json, status, error_message, now_iso))

    return {
        "event_id": event_id,
        "project_id": project_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "operation": operation,
        "payload": payload,
        "status": status,
        "retry_count": 0,
        "error_message": error_message,
        "created_at": now_iso,
        "synced_at": None,
    }


def list_pending_sync_outbox_events_db(
    limit: int = 50,
    project_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    query = "SELECT * FROM sync_outbox WHERE status = 'PENDING'"
    params = []
    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    query += " ORDER BY created_at ASC LIMIT ?;"
    params.append(limit)

    cursor.execute(query, tuple(params))
    out = []
    for r in cursor.fetchall():
        d = dict(r)
        try:
            d["payload"] = json.loads(d.get("payload_json") or "{}")
        except Exception:
            d["payload"] = {}
        out.append(d)
    return out


def list_sync_outbox_events_db(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    query = "SELECT * FROM sync_outbox WHERE 1=1"
    params = []
    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?;"
    params.append(limit)

    cursor.execute(query, tuple(params))
    out = []
    for r in cursor.fetchall():
        d = dict(r)
        try:
            d["payload"] = json.loads(d.get("payload_json") or "{}")
        except Exception:
            d["payload"] = {}
        out.append(d)
    return out


def update_sync_outbox_event_db(
    event_id: str,
    status: str,
    error_message: str = "",
    increment_retry: bool = False,
    synced: bool = False,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    import datetime
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat() if synced else None
    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        retry_fragment = "retry_count = retry_count + 1," if increment_retry else ""
        cursor.execute(f"""
            UPDATE sync_outbox
            SET status = ?,
                error_message = ?,
                {retry_fragment}
                synced_at = COALESCE(?, synced_at)
            WHERE event_id = ?;
        """, (status, error_message, now_iso, event_id))
        return cursor.rowcount > 0


# ==============================================================================
# Phase 6: Snowball Runs & Candidates Persistence
# ==============================================================================

def save_snowball_run_db(
    run_id: str,
    review_id: str,
    brief_id: str,
    config: dict,
    stopping_reason: str,
    total_rounds: int,
    total_candidates: int,
    unique_candidates: int,
    rounds_summary: list,
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    import datetime
    import json
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    config_json = json.dumps(config)
    summary_json = json.dumps(rounds_summary)

    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        actual_review_id = review_id
        if review_id:
            cursor.execute("SELECT review_id FROM prisma_reviews WHERE review_id = ?;", (review_id,))
            if not cursor.fetchone():
                actual_review_id = None

        cursor.execute("""
            INSERT INTO snowball_runs (
                run_id, review_id, brief_id, config_json, stopping_reason,
                total_rounds, total_candidates, unique_candidates, rounds_summary_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (run_id, actual_review_id, brief_id, config_json, stopping_reason,
              total_rounds, total_candidates, unique_candidates, summary_json, now_iso))

    return {
        "run_id": run_id,
        "review_id": review_id,
        "brief_id": brief_id,
        "config": config,
        "stopping_reason": stopping_reason,
        "total_rounds": total_rounds,
        "total_candidates": total_candidates,
        "unique_candidates": unique_candidates,
        "rounds_summary": rounds_summary,
        "created_at": now_iso,
    }


def get_snowball_run_db(
    run_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM snowball_runs WHERE run_id = ?;", (run_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["config"] = json.loads(d.get("config_json") or "{}")
        d["rounds_summary"] = json.loads(d.get("rounds_summary_json") or "[]")
    except Exception:
        d["config"] = {}
        d["rounds_summary"] = []
    return d


def list_snowball_runs_db(
    review_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM snowball_runs WHERE review_id = ? ORDER BY created_at DESC;",
        (review_id,),
    )
    out = []
    for r in cursor.fetchall():
        d = dict(r)
        try:
            d["config"] = json.loads(d.get("config_json") or "{}")
            d["rounds_summary"] = json.loads(d.get("rounds_summary_json") or "[]")
        except Exception:
            d["config"] = {}
            d["rounds_summary"] = []
        out.append(d)
    return out


def add_snowball_candidate_db(
    candidate_id: str,
    run_id: str,
    review_id: str,
    parent_paper_id: str,
    paper_id: str,
    title: str,
    direction: str,
    round_number: int,
    provider: str,
    doi: str = "",
    lookup_params: Optional[dict] = None,
    is_duplicate: bool = False,
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    import datetime
    import json
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    params_json = json.dumps(lookup_params or {})

    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO snowball_candidates (
                candidate_id, run_id, review_id, parent_paper_id, paper_id,
                title, doi, direction, round_number, provider, lookup_params_json,
                is_duplicate, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (candidate_id, run_id, review_id, parent_paper_id, paper_id,
              title, doi, direction, round_number, provider, params_json,
              1 if is_duplicate else 0, now_iso))

    return {
        "candidate_id": candidate_id,
        "run_id": run_id,
        "review_id": review_id,
        "parent_paper_id": parent_paper_id,
        "paper_id": paper_id,
        "title": title,
        "doi": doi,
        "direction": direction,
        "round_number": round_number,
        "provider": provider,
        "lookup_params": lookup_params or {},
        "is_duplicate": is_duplicate,
        "created_at": now_iso,
    }


def list_snowball_candidates_db(
    run_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM snowball_candidates WHERE run_id = ? ORDER BY round_number ASC, created_at ASC;",
        (run_id,),
    )
    out = []
    for r in cursor.fetchall():
        d = dict(r)
        d["is_duplicate"] = bool(d.get("is_duplicate"))
        try:
            d["lookup_params"] = json.loads(d.get("lookup_params_json") or "{}")
        except Exception:
            d["lookup_params"] = {}
        out.append(d)
    return out


# ==============================================================================
# Phase 7: Literature Clustering & Citation Graph Persistence
# ==============================================================================

def save_literature_clustering_db(
    clustering_data: dict,
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    import datetime
    import json
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cluster_run_id = clustering_data.get("cluster_run_id") or f"clust-{now_iso}"
    review_id = clustering_data["review_id"]
    project_id = clustering_data.get("project_id")
    algorithm = clustering_data.get("algorithm", "TFIDF_KMEANS")
    num_clusters = int(clustering_data.get("num_clusters", 0))
    clusters_json = clustering_data.get("clusters_json")
    if not isinstance(clusters_json, str):
        clusters_json = json.dumps(clustering_data.get("clusters", []))
    summary = clustering_data.get("summary", "")
    created_at = clustering_data.get("created_at") or now_iso

    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO literature_clusters (
                cluster_run_id, review_id, project_id, algorithm,
                num_clusters, clusters_json, summary, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cluster_run_id) DO UPDATE SET
                algorithm = excluded.algorithm,
                num_clusters = excluded.num_clusters,
                clusters_json = excluded.clusters_json,
                summary = excluded.summary;
        """, (cluster_run_id, review_id, project_id, algorithm,
              num_clusters, clusters_json, summary, created_at))

    return {
        "cluster_run_id": cluster_run_id,
        "review_id": review_id,
        "project_id": project_id,
        "algorithm": algorithm,
        "num_clusters": num_clusters,
        "clusters_json": clusters_json,
        "summary": summary,
        "created_at": created_at,
    }


def get_literature_clustering_db(
    review_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM literature_clusters
        WHERE review_id = ?
        ORDER BY created_at DESC
        LIMIT 1;
    """, (review_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["clusters"] = json.loads(d.get("clusters_json") or "[]")
    except Exception:
        d["clusters"] = []
    return d


def list_literature_clusterings_db(
    review_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM literature_clusters
        WHERE review_id = ?
        ORDER BY created_at DESC;
    """, (review_id,))
    out = []
    for row in cursor.fetchall():
        d = dict(row)
        try:
            d["clusters"] = json.loads(d.get("clusters_json") or "[]")
        except Exception:
            d["clusters"] = []
        out.append(d)
    return out


def save_citation_graph_db(
    graph_data: dict,
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    import datetime
    import json
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    graph_id = graph_data.get("graph_id") or f"graph-{now_iso}"
    review_id = graph_data["review_id"]
    project_id = graph_data.get("project_id")

    nodes_json = graph_data.get("nodes_json")
    if not isinstance(nodes_json, str):
        nodes_json = json.dumps(graph_data.get("nodes", []))

    edges_json = graph_data.get("edges_json")
    if not isinstance(edges_json, str):
        edges_json = json.dumps(graph_data.get("edges", []))

    bridge_papers_json = graph_data.get("bridge_papers_json")
    if not isinstance(bridge_papers_json, str):
        bridge_papers_json = json.dumps(graph_data.get("bridge_papers", []))

    structural_holes_json = graph_data.get("structural_holes_json")
    if not isinstance(structural_holes_json, str):
        structural_holes_json = json.dumps(graph_data.get("structural_holes", []))

    metrics_json = graph_data.get("metrics_json")
    if not isinstance(metrics_json, str):
        metrics_json = json.dumps(graph_data.get("metrics", {}))

    created_at = graph_data.get("created_at") or now_iso

    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO citation_graphs (
                graph_id, review_id, project_id, nodes_json, edges_json,
                bridge_papers_json, structural_holes_json, metrics_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(graph_id) DO UPDATE SET
                nodes_json = excluded.nodes_json,
                edges_json = excluded.edges_json,
                bridge_papers_json = excluded.bridge_papers_json,
                structural_holes_json = excluded.structural_holes_json,
                metrics_json = excluded.metrics_json;
        """, (graph_id, review_id, project_id, nodes_json, edges_json,
              bridge_papers_json, structural_holes_json, metrics_json, created_at))

    return {
        "graph_id": graph_id,
        "review_id": review_id,
        "project_id": project_id,
        "nodes_json": nodes_json,
        "edges_json": edges_json,
        "bridge_papers_json": bridge_papers_json,
        "structural_holes_json": structural_holes_json,
        "metrics_json": metrics_json,
        "created_at": created_at,
    }


def get_citation_graph_db(
    review_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM citation_graphs
        WHERE review_id = ?
        ORDER BY created_at DESC
        LIMIT 1;
    """, (review_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["nodes"] = json.loads(d.get("nodes_json") or "[]")
        d["edges"] = json.loads(d.get("edges_json") or "[]")
        d["bridge_papers"] = json.loads(d.get("bridge_papers_json") or "[]")
        d["structural_holes"] = json.loads(d.get("structural_holes_json") or "[]")
        d["metrics"] = json.loads(d.get("metrics_json") or "{}")
    except Exception:
        d["nodes"] = []
        d["edges"] = []
        d["bridge_papers"] = []
        d["structural_holes"] = []
        d["metrics"] = {}
    return d


def get_project_literature_map_db(
    project_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    # Find all reviews for project
    cursor.execute("""
        SELECT review_id, topic FROM prisma_reviews
        WHERE project_id = ?
        ORDER BY created_at DESC;
    """, (project_id,))
    reviews = [dict(r) for r in cursor.fetchall()]

    all_clusters = []
    all_graphs = []
    for rev in reviews:
        c = get_literature_clustering_db(rev["review_id"], db_path=db_path)
        if c:
            all_clusters.append(c)
        g = get_citation_graph_db(rev["review_id"], db_path=db_path)
        if g:
            all_graphs.append(g)

    # Also find clusters directly associated with project_id
    cursor.execute("""
        SELECT cluster_run_id FROM literature_clusters
        WHERE project_id = ?
        ORDER BY created_at DESC;
    """, (project_id,))
    for row in cursor.fetchall():
        run_id = row["cluster_run_id"]
        if not any(c.get("cluster_run_id") == run_id for c in all_clusters):
            cur2 = conn.execute("SELECT * FROM literature_clusters WHERE cluster_run_id = ?", (run_id,))
            c_row = cur2.fetchone()
            if c_row:
                d = dict(c_row)
                d["clusters"] = json.loads(d.get("clusters_json") or "[]")
                all_clusters.append(d)

    # Also find citation graphs directly associated with project_id
    cursor.execute("""
        SELECT graph_id FROM citation_graphs
        WHERE project_id = ?
        ORDER BY created_at DESC;
    """, (project_id,))
    for row in cursor.fetchall():
        gid = row["graph_id"]
        if not any(g.get("graph_id") == gid for g in all_graphs):
            cur2 = conn.execute("SELECT * FROM citation_graphs WHERE graph_id = ?", (gid,))
            g_row = cur2.fetchone()
            if g_row:
                gd = dict(g_row)
                gd["nodes"] = json.loads(gd.get("nodes_json") or "[]")
                gd["edges"] = json.loads(gd.get("edges_json") or "[]")
                gd["bridge_papers"] = json.loads(gd.get("bridge_papers_json") or "[]")
                gd["structural_holes"] = json.loads(gd.get("structural_holes_json") or "[]")
                gd["metrics"] = json.loads(gd.get("metrics_json") or "{}")
                all_graphs.append(gd)

    return {
        "project_id": project_id,
        "reviews": reviews,
        "clusterings": all_clusters,
        "graphs": all_graphs,
    }


# ==============================================================================
# Phase 7: Journal Submission Persistence
# ==============================================================================

def save_journal_submission_db(
    submission_data: dict,
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    import datetime
    import json
    init_db(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    submission_id = submission_data["submission_id"]
    manuscript_id = submission_data["manuscript_id"]
    version = int(submission_data["version"])
    preset = submission_data["preset"]
    is_anonymized = 1 if submission_data.get("is_anonymized") else 0
    package_filename = submission_data.get("package_filename", f"{submission_id}.zip")
    manifest_json = submission_data.get("manifest_json")
    if not isinstance(manifest_json, str):
        manifest_json = json.dumps(submission_data.get("manifest", {}))
    checklist_md = submission_data.get("checklist_md", "")
    created_at = submission_data.get("created_at") or now_iso

    conn = get_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO journal_submissions (
                submission_id, manuscript_id, version, preset, is_anonymized,
                package_filename, manifest_json, checklist_md, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(submission_id) DO UPDATE SET
                preset = excluded.preset,
                manifest_json = excluded.manifest_json,
                checklist_md = excluded.checklist_md;
        """, (submission_id, manuscript_id, version, preset, is_anonymized,
              package_filename, manifest_json, checklist_md, created_at))

    return {
        "submission_id": submission_id,
        "manuscript_id": manuscript_id,
        "version": version,
        "preset": preset,
        "is_anonymized": is_anonymized,
        "package_filename": package_filename,
        "manifest_json": manifest_json,
        "checklist_md": checklist_md,
        "created_at": created_at,
    }


def get_journal_submission_db(
    submission_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM journal_submissions WHERE submission_id = ?;", (submission_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["manifest"] = json.loads(d.get("manifest_json") or "{}")
    except Exception:
        d["manifest"] = {}
    return d


def list_journal_submissions_db(
    manuscript_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    import json
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM journal_submissions
        WHERE manuscript_id = ?
        ORDER BY created_at DESC;
    """, (manuscript_id,))
    out = []
    for r in cursor.fetchall():
        d = dict(r)
        try:
            d["manifest"] = json.loads(d.get("manifest_json") or "{}")
        except Exception:
            d["manifest"] = {}
        out.append(d)
    return out





