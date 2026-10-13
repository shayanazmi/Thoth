#!/usr/bin/env python3
"""
Thoth Database Migration Tool: SQLite to Supabase / PostgreSQL.

Reads sessions and reports from local SQLite store.db and migrates them
into Supabase Postgres with schema compatibility and conflict resolution.

Usage:
    python scripts/db/migrate_sqlite_to_supabase.py [--sqlite-path store.db] [--dry-run]
"""

import os
import sys
import sqlite3
import argparse
import json
import logging
from typing import List, Dict, Any, Optional

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from backend.core.config import get_settings
from backend.core.logging import get_logger

logger = get_logger("ThothMigration")

def load_sqlite_data(sqlite_path: str) -> Dict[str, List[Dict[str, Any]]]:
    if not os.path.exists(sqlite_path):
        logger.warning(f"SQLite database not found at '{sqlite_path}'.")
        return {"sessions": [], "reports": []}

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sessions = []
    try:
        cursor.execute("SELECT * FROM sessions")
        for row in cursor.fetchall():
            d = dict(row)
            sid = d.get("session_id") or d.get("id")
            topic = d.get("title") or d.get("topic") or "Untitled Session"
            state = {}
            if "metadata" in d and d["metadata"]:
                try:
                    state = json.loads(d["metadata"]) if isinstance(d["metadata"], str) else d["metadata"]
                except Exception:
                    pass
            elif "state" in d and d["state"]:
                try:
                    state = json.loads(d["state"]) if isinstance(d["state"], str) else d["state"]
                except Exception:
                    pass

            sessions.append({
                "id": sid,
                "topic": topic,
                "status": d.get("status", "completed"),
                "state": state,
                "created_at": d.get("created_at"),
                "updated_at": d.get("updated_at") or d.get("created_at"),
            })
    except sqlite3.OperationalError as e:
        logger.info(f"Note: Could not query 'sessions' table: {e}")

    reports = []
    try:
        cursor.execute("SELECT * FROM reports")
        for row in cursor.fetchall():
            d = dict(row)
            rid = d.get("report_id") or d.get("id")
            content = d.get("content") or d.get("markdown") or ""
            reports.append({
                "id": rid,
                "session_id": d.get("session_id"),
                "topic": d.get("topic", "Untitled Report"),
                "markdown": content,
                "sources": d.get("sources", []),
                "created_at": d.get("created_at"),
            })
    except sqlite3.OperationalError as e:
        logger.info(f"Note: Could not query 'reports' table: {e}")

    conn.close()
    return {"sessions": sessions, "reports": reports}

def migrate_to_supabase(
    sessions: List[Dict[str, Any]],
    reports: List[Dict[str, Any]],
    dry_run: bool = False
) -> Dict[str, int]:
    settings = get_settings()
    results = {"sessions_migrated": 0, "reports_migrated": 0, "errors": 0}

    logger.info(f"Loaded {len(sessions)} sessions and {len(reports)} reports from SQLite.")

    if dry_run:
        logger.info("[DRY RUN] Previewing migration (no writes will be performed):")
        for s in sessions[:3]:
            logger.info(f"  Session sample: id={s.get('id')} topic={s.get('topic')}")
        for r in reports[:3]:
            logger.info(f"  Report sample: id={r.get('id')} session_id={r.get('session_id')}")
        results["sessions_migrated"] = len(sessions)
        results["reports_migrated"] = len(reports)
        return results

    # Check for Supabase client
    try:
        from supabase import create_client
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            logger.error("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing. Migration requires service role key.")
            results["errors"] += 1
            return results

        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    except ImportError:
        logger.warning("'supabase' package not installed. Testing in direct mock / fallback mode.")
        client = None

    if client:
        # Migrate sessions
        for s in sessions:
            try:
                payload = {
                    "id": s.get("id"),
                    "title": s.get("topic") or s.get("title") or "Untitled Research",
                    "summary": s.get("summary", ""),
                    "metadata": {
                        "status": s.get("status", "completed"),
                        "state": s.get("state", {})
                    },
                    "created_at": s.get("created_at"),
                    "updated_at": s.get("updated_at"),
                }
                client.table("sessions").upsert(payload).execute()
                results["sessions_migrated"] += 1
            except Exception as e:
                logger.error(f"Error migrating session {s.get('id')}: {e}")
                results["errors"] += 1

        # Migrate reports
        for r in reports:
            try:
                payload = {
                    "id": r.get("id"),
                    "session_id": r.get("session_id"),
                    "topic": r.get("topic", "Untitled Report"),
                    "content": r.get("markdown") or r.get("report") or r.get("content") or "",
                    "score": float(r.get("score", 0.0) or 0.0),
                    "verifier_feedback": r.get("verifier_feedback", ""),
                    "mindmap": r.get("mindmap", {}),
                    "created_at": r.get("created_at"),
                }
                client.table("reports").upsert(payload).execute()
                results["reports_migrated"] += 1
            except Exception as e:
                logger.error(f"Error migrating report {r.get('id')}: {e}")
                results["errors"] += 1

    return results

def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite store.db to Supabase Postgres")
    default_db = os.path.join(_PROJECT_ROOT, "db", "store.db")
    if not os.path.exists(default_db):
        default_db = os.path.join(_PROJECT_ROOT, "store.db")
    parser.add_argument("--sqlite-path", default=default_db, help="Path to SQLite store.db")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and count records without writing")
    args = parser.parse_args()

    print("=" * 70)
    print("THOTH DATABASE MIGRATION: SQLite -> Supabase")
    print("=" * 70)

    data = load_sqlite_data(args.sqlite_path)
    res = migrate_to_supabase(data["sessions"], data["reports"], dry_run=args.dry_run)

    print("\nMigration Results:")
    print(f"  Sessions migrated: {res['sessions_migrated']}")
    print(f"  Reports migrated:  {res['reports_migrated']}")
    print(f"  Errors:            {res['errors']}")
    print("=" * 70)

if __name__ == "__main__":
    main()
