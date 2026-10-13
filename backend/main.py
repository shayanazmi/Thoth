import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.core.errors import register_exception_handlers
from backend.core.cache import cache_manager

from backend.api.routes_health import router as health_router
from backend.api.routes_research import router as research_router, is_casual_query
from backend.api.routes_followup import router as followup_router
from backend.api.routes_brainstorm import router as brainstorm_router
from backend.api.routes_vault import router as vault_router

logger = get_logger("ThothApp")

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(f"Initializing Thoth Research Intelligence Service (env={settings.ENVIRONMENT})...")
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

# Global Exception Handlers
register_exception_handlers(app)

# Include API Routers
app.include_router(health_router)
app.include_router(research_router)
app.include_router(followup_router)
app.include_router(brainstorm_router)
app.include_router(vault_router)

# Mount local frontend if available
_WEB_DIR = os.path.join(_PROJECT_ROOT, "web")
if os.path.exists(_WEB_DIR):
    for sub in ["styles", "lib", "components", "pages", "css", "js", "assets"]:
        subdir = os.path.join(_WEB_DIR, sub)
        if os.path.exists(subdir):
            app.mount(f"/{sub}", StaticFiles(directory=subdir), name=sub)

    @app.get("/", response_class=HTMLResponse)
    async def serve_index():
        index_file = os.path.join(_WEB_DIR, "index.html")
        if os.path.exists(index_file):
            with open(index_file, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse("<h1>Thoth Studio index.html not found.</h1>", status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=False)
