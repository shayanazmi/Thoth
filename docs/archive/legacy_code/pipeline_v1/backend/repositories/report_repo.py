import datetime
from typing import Optional, Dict, Any, List
from backend.repositories.base import supabase_provider
from backend.core.logging import get_logger

logger = get_logger("ReportRepository")

class ReportRepository:
    def __init__(self):
        self.provider = supabase_provider

    async def save_report(
        self,
        report_id: str,
        session_id: str,
        user_id: str,
        topic: str,
        content: str,
        score: float = 0.0,
        verifier_feedback: str = "",
        mindmap: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        client = self.provider.get_client()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if client:
            try:
                row = {
                    "id": report_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "topic": topic,
                    "content": content,
                    "score": score,
                    "verifier_feedback": verifier_feedback,
                    "mindmap": mindmap or {},
                    "created_at": now_iso
                }
                res = client.table("reports").upsert(row).execute()
                return res.data[0] if res.data else row
            except Exception as e:
                logger.error(f"Supabase error saving report {report_id}: {e}")

        from backend.memory.db import save_report as sqlite_save_report
        return sqlite_save_report(
            report_id=report_id,
            session_id=session_id,
            topic=topic,
            content=content,
            score=score,
            verifier_feedback=verifier_feedback,
            mindmap=mindmap
        )

    async def list_reports(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        client = self.provider.get_client()
        if client:
            try:
                res = client.table("reports").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
                return res.data or []
            except Exception as e:
                logger.error(f"Supabase error listing reports: {e}")

        from backend.memory.db import list_reports as sqlite_list_reports
        return sqlite_list_reports(limit=limit)

report_repo = ReportRepository()
