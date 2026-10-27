import datetime
from typing import Optional, Dict, Any, List
from backend.repositories.base import supabase_provider
from backend.core.logging import get_logger

logger = get_logger("VaultRepository")

class VaultRepository:
    def __init__(self):
        self.provider = supabase_provider

    async def save_note(
        self,
        note_id: str,
        user_id: str,
        note_type: str,
        title: str,
        content: str,
        confidence: float = 1.0
    ) -> Dict[str, Any]:
        client = self.provider.get_client()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if client:
            try:
                row = {
                    "note_id": note_id,
                    "user_id": user_id,
                    "type": note_type,
                    "title": title,
                    "content": content,
                    "confidence": confidence,
                    "updated_at": now_iso
                }
                res = client.table("notes").upsert(row).execute()
                return res.data[0] if res.data else row
            except Exception as e:
                logger.error(f"Supabase error saving note {note_id}: {e}")

        # Fallback to local vault markdown / sqlite
        from backend.memory.vault import write_note
        from backend.memory.db import insert_note
        write_note(note_id, content, note_type)
        insert_note(note_id, note_type, now_iso, confidence)
        return {"note_id": note_id, "type": note_type, "content": content}

    async def list_notes(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        client = self.provider.get_client()
        if client:
            try:
                res = client.table("notes").select("note_id, type, title, created_at").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
                return res.data or []
            except Exception as e:
                logger.error(f"Supabase error listing notes: {e}")

        from backend.memory.vault import list_notes as local_list_notes
        return local_list_notes()

    async def get_note(self, note_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        client = self.provider.get_client()
        if client:
            try:
                res = client.table("notes").select("*").eq("note_id", note_id).execute()
                if res.data:
                    return res.data[0]
            except Exception as e:
                logger.error(f"Supabase error getting note {note_id}: {e}")

        from backend.memory.vault import read_note as local_read_note
        content = local_read_note(note_id)
        if content:
            return {"note_id": note_id, "content": content}
        return None

    async def save_edge(
        self,
        source_note: str,
        relation: str,
        target_note: str,
        user_id: str,
        confidence: float = 1.0
    ) -> None:
        client = self.provider.get_client()
        if client:
            try:
                row = {
                    "source_note": source_note,
                    "relation": relation,
                    "target_note": target_note,
                    "user_id": user_id,
                    "confidence": confidence
                }
                client.table("edges").upsert(row).execute()
                return
            except Exception as e:
                logger.error(f"Supabase error saving edge: {e}")

        from backend.memory.db import insert_edge
        insert_edge(source_note, relation, target_note, confidence)

vault_repo = VaultRepository()
