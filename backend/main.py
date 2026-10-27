import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
for _p in (_CURRENT_DIR, _PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Ensure 'backend' package is resolvable when rootDirectory is deployed as /backend
_backend_symlink = os.path.join(_CURRENT_DIR, "backend")
if not os.path.exists(_backend_symlink):
    try:
        os.symlink(_CURRENT_DIR, _backend_symlink)
    except Exception:
        pass

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.core.errors import register_exception_handlers
from backend.core.cache import cache_manager

from backend.api.routes_health import router as health_router
from backend.api.routes_thinkers import router as thinkers_router
from backend.api.routes_trial import router as trial_router
from backend.api.routes_design import router as design_router
from backend.api.routes_review import router as review_router
from backend.api.routes_proposal import router as proposal_router
from backend.api.routes_workspace import router as workspace_router
from backend.api.routes_chat import router as chat_router

logger = get_logger("ThothApp")

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(f"Initializing Thoth Research Intelligence Service (env={settings.ENVIRONMENT})...")
    # Initialize SQLite database schema idempotently
    from backend.memory.db import init_db
    init_db()
    # Startup reconciliation: reconcile abandoned tasks from prior process sessions
    from backend.conversation.brief import task_manager
    orphaned_count = task_manager.reconcile_orphaned_tasks()
    if orphaned_count > 0:
        logger.warning(f"[RECOVERY] Reconciled {orphaned_count} abandoned/interrupted research task(s) into FAILED_ORPHANED state.")
    from backend.research.store import reconcile_orphaned_trials
    from backend.research.review_store import reconcile_orphaned as reconcile_orphaned_reviews
    if reconcile_orphaned_reviews():
        logger.warning("[RECOVERY] Marked systematic review(s) interrupted by a restart as stopped.")
    stopped = reconcile_orphaned_trials()
    if stopped:
        logger.warning(f"[RECOVERY] Marked {stopped} trial(s) interrupted by a restart as stopped.")
    # Verify Redis connectivity in background
    try:
        await cache_manager.get_client()
    except Exception as e:
        logger.warning(f"Initial Redis check: {e}")
    yield
    logger.info("Shutting down Thoth Research Intelligence Service...")

settings = get_settings()

app = FastAPI(
    title="Thoth Research Gateway",
    description="Autonomous Multi-Agent Academic Intelligence & Grounding Engine",
    version="3.0.0",
    lifespan=lifespan
)

# CORS Policy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The UI is plain ES modules imported without version tags; make browsers revalidate them
# (unchanged files come back as 304) so a reload never mixes old and new modules.
@app.middleware("http")
async def revalidate_frontend_assets(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/js/", "/styles/", "/scripted/")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache"
    return response

# Global Exception Handlers
register_exception_handlers(app)

# Include API Routers
app.include_router(health_router)
app.include_router(thinkers_router)
app.include_router(trial_router)
app.include_router(design_router)
app.include_router(review_router)
app.include_router(proposal_router)
app.include_router(workspace_router)
app.include_router(chat_router)


# Mount local frontend if available
_FRONTEND_DIR = os.path.join(_PROJECT_ROOT, "frontend")
if not os.path.exists(_FRONTEND_DIR):
    _FRONTEND_DIR = os.path.join(_PROJECT_ROOT, "web")

if os.path.exists(_FRONTEND_DIR):
    # "scripted" is the optional guided tour; when that folder is deleted it is simply skipped.
    for sub in ["styles", "lib", "components", "js", "assets", "scripted"]:
        subdir = os.path.join(_FRONTEND_DIR, sub)
        if os.path.exists(subdir):
            app.mount(f"/{sub}", StaticFiles(directory=subdir), name=sub)

    @app.get("/", response_class=HTMLResponse)
    async def serve_index():
        index_file = os.path.join(_FRONTEND_DIR, "index.html")
        if os.path.exists(index_file):
            with open(index_file, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse("<h1>Thoth Studio index.html not found.</h1>", status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=False)
