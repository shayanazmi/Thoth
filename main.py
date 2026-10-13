"""
Thoth Main Entrypoint
Exposes the FastAPI application instance for ASGI servers and Railway deployments.
"""
from backend.main import app

__all__ = ["app"]
