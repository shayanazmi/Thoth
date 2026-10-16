"""
THOTH Cloud Synchronization & Outbox Queue Engine
Phase 6 — Deliverable C: Reliable PostgreSQL/Supabase synchronization with offline resilience.

Implements an outbox pattern with:
- Scoped queueing of entity mutations (projects, manuscripts, revisions, screening, exports).
- Offline-first local preservation: works completely offline without blocking research.
- Collision and conflict detection reusing Phase 5 base_version guards.
- Idempotent replay for Supabase/PostgreSQL destinations.
"""

from __future__ import annotations

import datetime
import json
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from backend.core.logging import get_logger
from backend.memory.db import (
    DEFAULT_DB_PATH,
    add_sync_outbox_event_db,
    list_pending_sync_outbox_events_db,
    list_sync_outbox_events_db,
    update_sync_outbox_event_db,
)

logger = get_logger("CollaborationSync")


class SyncOperation(str, Enum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class SyncStatus(str, Enum):
    PENDING = "PENDING"
    SYNCED = "SYNCED"
    FAILED = "FAILED"
    CONFLICT = "CONFLICT"


class SyncOutboxEvent(BaseModel):
    event_id: str
    project_id: Optional[str] = None
    entity_type: str
    entity_id: str
    operation: SyncOperation
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: SyncStatus = SyncStatus.PENDING
    retry_count: int = 0
    error_message: str = ""
    created_at: str
    synced_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "project_id": self.project_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "operation": self.operation.value,
            "payload": self.payload,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "synced_at": self.synced_at,
        }


def queue_sync_event(
    entity_type: str,
    entity_id: str,
    operation: SyncOperation | str,
    payload: Dict[str, Any],
    project_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> SyncOutboxEvent:
    """
    Durable outbox enqueue. Records local mutation to sync_outbox table.
    Enables local-first operations to persist reliably even if cloud is disconnected.
    """
    op_enum = SyncOperation(operation) if isinstance(operation, str) else operation
    event_id = f"evt_{uuid.uuid4().hex[:10]}"

    rec = add_sync_outbox_event_db(
        event_id=event_id,
        entity_type=entity_type,
        entity_id=entity_id,
        operation=op_enum.value,
        payload=payload,
        project_id=project_id,
        status=SyncStatus.PENDING.value,
        db_path=db_path,
    )

    return SyncOutboxEvent(
        event_id=rec["event_id"],
        project_id=rec.get("project_id"),
        entity_type=rec["entity_type"],
        entity_id=rec["entity_id"],
        operation=op_enum,
        payload=rec.get("payload") or {},
        status=SyncStatus.PENDING,
        retry_count=rec.get("retry_count", 0),
        error_message="",
        created_at=rec["created_at"],
    )


def replay_sync_outbox(
    supabase_client: Optional[Any] = None,
    project_id: Optional[str] = None,
    limit: int = 50,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """
    Replays pending outbox events against remote PostgreSQL/Supabase target.
    If supabase_client is not configured, preserves local state without raising errors.
    Detects version conflicts before applying mutations.
    """
    pending = list_pending_sync_outbox_events_db(limit=limit, project_id=project_id, db_path=db_path)
    if not pending:
        return {"processed": 0, "synced": 0, "conflicts": 0, "failures": 0, "events": []}

    if supabase_client is None:
        logger.info(f"[OUTBOX] {len(pending)} event(s) queued. Supabase client unconfigured (offline-first mode).")
        return {
            "processed": len(pending),
            "synced": 0,
            "conflicts": 0,
            "failures": 0,
            "offline_mode": True,
            "message": "Offline-first mode active. Events remain durable in local outbox queue.",
            "events": pending,
        }

    synced_count = 0
    conflict_count = 0
    failure_count = 0
    results = []

    for event in pending:
        event_id = event["event_id"]
        entity_type = event["entity_type"]
        entity_id = event["entity_id"]
        op = event["operation"]
        payload = event.get("payload") or {}

        try:
            # Conflict Detection on Manuscript Revisions
            if entity_type == "manuscript_revisions" and "base_version" in payload:
                base_ver = payload.get("base_version")
                # Query remote current version if client supports it
                if hasattr(supabase_client, "table"):
                    remote_res = supabase_client.table("manuscript_revisions") \
                        .select("version") \
                        .eq("manuscript_id", payload.get("manuscript_id")) \
                        .order("version", desc=True) \
                        .limit(1) \
                        .execute()
                    if remote_res and getattr(remote_res, "data", None):
                        latest_remote_ver = remote_res.data[0]["version"]
                        if base_ver is not None and latest_remote_ver > base_ver:
                            err_msg = (
                                f"Remote revision conflict: local base_version v{base_ver} "
                                f"is superseded by remote v{latest_remote_ver}."
                            )
                            update_sync_outbox_event_db(
                                event_id=event_id,
                                status=SyncStatus.CONFLICT.value,
                                error_message=err_msg,
                                db_path=db_path,
                            )
                            conflict_count += 1
                            results.append({"event_id": event_id, "status": "CONFLICT", "error": err_msg})
                            continue

            # Execute remote sync operation
            table_name = entity_type
            if hasattr(supabase_client, "table"):
                tbl = supabase_client.table(table_name)
                if op == SyncOperation.INSERT.value:
                    tbl.upsert(payload).execute()
                elif op == SyncOperation.UPDATE.value:
                    tbl.update(payload).eq("id" if "id" in payload else f"{entity_type[:-1]}_id", entity_id).execute()
                elif op == SyncOperation.DELETE.value:
                    tbl.delete().eq("id" if "id" in payload else f"{entity_type[:-1]}_id", entity_id).execute()

            # Mark as successfully synced
            update_sync_outbox_event_db(
                event_id=event_id,
                status=SyncStatus.SYNCED.value,
                synced=True,
                db_path=db_path,
            )
            synced_count += 1
            results.append({"event_id": event_id, "status": "SYNCED"})

        except Exception as e:
            err_str = str(e)
            logger.error(f"[SYNC] Error syncing event {event_id}: {err_str}")
            update_sync_outbox_event_db(
                event_id=event_id,
                status=SyncStatus.FAILED.value,
                error_message=err_str,
                increment_retry=True,
                db_path=db_path,
            )
            failure_count += 1
            results.append({"event_id": event_id, "status": "FAILED", "error": err_str})

    return {
        "processed": len(pending),
        "synced": synced_count,
        "conflicts": conflict_count,
        "failures": failure_count,
        "results": results,
    }


def get_project_sync_status(
    project_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Retrieves sync outbox status and recent activity for a project."""
    all_events = list_sync_outbox_events_db(project_id=project_id, limit=100, db_path=db_path)
    pending = [e for e in all_events if e.get("status") == SyncStatus.PENDING.value]
    synced = [e for e in all_events if e.get("status") == SyncStatus.SYNCED.value]
    conflicts = [e for e in all_events if e.get("status") == SyncStatus.CONFLICT.value]
    failed = [e for e in all_events if e.get("status") == SyncStatus.FAILED.value]

    return {
        "project_id": project_id,
        "total_events": len(all_events),
        "pending_count": len(pending),
        "synced_count": len(synced),
        "conflict_count": len(conflicts),
        "failed_count": len(failed),
        "recent_events": all_events[:10],
    }
