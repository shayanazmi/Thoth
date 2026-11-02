# Thoth · Developed by Shayan Azmi
"""Health and status: /health (liveness), /ready (storage), /api/status (models and circuit breakers)."""
import datetime
import os

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
def api_health():
    return {"status": "ok", "app": "Thoth"}


@router.get("/ready")
def readiness_probe():
    from backend.memory import db
    return {"status": "ready", "database": "sqlite", "database_path": db.DEFAULT_DB_PATH,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}


@router.get("/api/status")
def api_status():
    from backend.dispatcher import default_dispatcher, scholarly_dispatcher, s2_dispatcher
    return {
        "status": "online",
        "circuit_breaker_state": default_dispatcher._state,
        "scholarly_breaker_state": scholarly_dispatcher._state,
        "s2_breaker_state": s2_dispatcher._state,
        "primary_provider": "NVIDIA NIM",
        "primary_model": os.getenv("NVIDIA_PRIMARY_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b"),
        "fallback_provider": "Groq / OpenAI",
        "fallback_model": os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-120b"),
    }
