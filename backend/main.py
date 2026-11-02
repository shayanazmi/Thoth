"""Thoth, a research companion: the FastAPI application. Serves the API and the browser UI.

Developed by Shayan Azmi.
"""
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.core.errors import register_exception_handlers

from backend.api.routes_health import router as health_router
from backend.api.routes_thinkers import router as thinkers_router
from backend.api.routes_trial import router as trial_router
from backend.api.routes_design import router as design_router
from backend.api.routes_review import router as review_router
from backend.api.routes_proposal import router as proposal_router
from backend.api.routes_projects import router as projects_router
from backend.api.routes_chat import router as chat_router

logger = get_logger("Thoth")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(f"Starting Thoth (env={settings.ENVIRONMENT})...")
    from backend.memory.db import init_db
    init_db()
    # Work interrupted by a restart is marked stopped, never left "running".
    from backend.research.store import reconcile_orphaned_trials
    from backend.research.review_store import reconcile_orphaned as reconcile_orphaned_reviews
    if reconcile_orphaned_reviews():
        logger.warning("Marked systematic review(s) interrupted by a restart as stopped.")
    stopped = reconcile_orphaned_trials()
    if stopped:
        logger.warning(f"Marked {stopped} trial(s) interrupted by a restart as stopped.")
    yield
    logger.info("Shutting down Thoth...")


settings = get_settings()

app = FastAPI(
    title="Thoth",
    description="A research companion: from a hunch to a defensible research proposal. Developed by Shayan Azmi.",
    version="1.0.0",
    lifespan=lifespan,
)

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


register_exception_handlers(app)

for router in (health_router, thinkers_router, trial_router, design_router, review_router,
               proposal_router, projects_router, chat_router):
    app.include_router(router)

_FRONTEND_DIR = os.path.join(_PROJECT_ROOT, "frontend")

if os.path.exists(_FRONTEND_DIR):
    # "scripted" is the optional guided tour; when that folder is deleted it is simply skipped.
    for sub in ["styles", "js", "assets", "scripted"]:
        subdir = os.path.join(_FRONTEND_DIR, sub)
        if os.path.exists(subdir):
            app.mount(f"/{sub}", StaticFiles(directory=subdir), name=sub)

    @app.get("/", response_class=HTMLResponse)
    async def serve_index():
        index_file = os.path.join(_FRONTEND_DIR, "index.html")
        if os.path.exists(index_file):
            with open(index_file, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse("<h1>frontend/index.html not found.</h1>", status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=False)
