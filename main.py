"""
Thoth Main Entrypoint
Exposes the FastAPI application instance for ASGI servers and Railway deployments.
"""
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.main import app

__all__ = ["app"]
