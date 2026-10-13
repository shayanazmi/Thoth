import os
import sys
import logging

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.main import app
from backend.api.routes_research import is_casual_query
from backend.agents import (
    direct_chat_chain,
    strip_chain_of_thought,
    sanitize_log_message,
)
from backend.orchestrator import stream_research_pipeline
from backend.pipeline import stream_followup_turn
from backend.conversation import detect_escalation_intent
from backend.memory.vault import list_notes, read_note, DEFAULT_VAULT_DIR

logger = logging.getLogger("ThothWebServer")

if __name__ == "__main__":
    import uvicorn
    from backend.core.config import get_settings
    settings = get_settings()
    port = int(os.getenv("PORT", settings.PORT))
    host = os.getenv("HOST", settings.HOST)
    uvicorn.run("backend.main:app", host=host, port=port, reload=False)
