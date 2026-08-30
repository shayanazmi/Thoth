"""
Thoth · Autonomous Research Intelligence Server
===============================================
Authoritative entrypoint launching the Starlette SSE Web Server and REST API.
"""

import os
import sys
import uvicorn

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from web_server import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    print(f"\n=======================================================")
    print(f"🪶  Thoth Autonomous Research Intelligence Studio")
    print(f"📡  Listening on: http://{host}:{port}")
    print(f"=======================================================\n")
    uvicorn.run("web_server:app", host=host, port=port, reload=False)