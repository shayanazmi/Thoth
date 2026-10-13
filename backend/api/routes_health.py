import datetime
from typing import Optional
from fastapi import APIRouter
from backend.core.cache import cache_manager
from backend.repositories.base import supabase_provider

router = APIRouter(tags=["Health & Diagnostics"])

@router.get("/health")
def api_health():
    return {"status": "ok", "app": "Thoth Research Intelligence"}

@router.get("/ready")
async def readiness_probe():
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    redis_ok = await cache_manager.is_connected()
    db_ok = supabase_provider.is_available()

    return {
        "status": "ready" if (redis_ok or True) else "degraded",
        "database": "supabase_connected" if db_ok else "sqlite_local",
        "redis": "connected" if redis_ok else "memory_fallback",
        "timestamp": now_iso
    }

@router.get("/api/status")
def api_status():
    from backend.telemetry import get_telemetry_status
    return get_telemetry_status()
