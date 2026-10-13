import datetime
from typing import Optional, Dict, Any, List
from backend.repositories.base import supabase_provider
from backend.core.logging import get_logger

logger = get_logger("SessionRepository")

class SessionRepository:
    def __init__(self):
        self.provider = supabase_provider

    async def save_session(
        self,
        session_id: str,
        user_id: str,
        title: str,
        summary: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        client = self.provider.get_client()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if client:
            try:
                row = {
                    "id": session_id,
                    "user_id": user_id,
                    "title": title,
                    "summary": summary,
                    "metadata": metadata or {},
                    "updated_at": now_iso
                }
                # Upsert into sessions
                res = client.table("sessions").upsert(row).execute()
                return res.data[0] if res.data else row
            except Exception as e:
                logger.error(f"Supabase error saving session {session_id}: {e}")

        # Fallback to local SQLite store
        from backend.memory.db import save_session as sqlite_save_session
        return sqlite_save_session(session_id=session_id, title=title, summary=summary, metadata=metadata)

    async def list_sessions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        client = self.provider.get_client()
        if client:
            try:
                res = client.table("sessions").select("*").eq("user_id", user_id).order("updated_at", desc=True).limit(limit).execute()
                return res.data or []
            except Exception as e:
                logger.error(f"Supabase error listing sessions: {e}")

        from backend.memory.db import list_sessions as sqlite_list_sessions
        return sqlite_list_sessions(limit=limit)

session_repo = SessionRepository()
