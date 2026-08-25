#!/usr/bin/env python3
"""
Thoth · One-Click Web Studio Launcher
======================================
Launches the FastAPI backend gateway and opens the browser to the 3D Research Studio.
"""

import os
import sys
import time
import webbrowser
import uvicorn
from dotenv import load_dotenv

import logging

# Load environment
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

# ── Silence third-party noise ────────────────────────────────────────────────
# deepeval emits "No Confident AI API key found" on every batch — we run in
# local offline mode intentionally, so this warning is pure spam.
logging.getLogger("confident").setLevel(logging.CRITICAL)
logging.getLogger("deepeval").setLevel(logging.WARNING)
# ─────────────────────────────────────────────────────────────────────────────

def main():
    host = "127.0.0.1"
    port = 8000
    url = f"http://{host}:{port}"

    print("=" * 80)
    print("THOTH · THE DIVINE SCRIBE (RESEARCH STUDIO & CHATBOT)")
    print("=" * 80)
    print(f"[INFO] Launching Web Gateway at {url} ...")
    print("[INFO] Press Ctrl+C in terminal to stop server.")
    print("=" * 80)

    # Open browser automatically after a short delay
    import threading
    def _open_browser():
        time.sleep(1.0)
        webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()

    from web_server import app
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    main()
