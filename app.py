"""
Thoth · Streamlit Application Launcher
=======================================
Authoritative entrypoint forwarding directly to the modular frontend command center (frontend/app.py).
"""

import os
import sys
import runpy

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_CANONICAL_APP = os.path.join(_PROJECT_ROOT, "frontend", "app.py")

# Execute canonical modular application
runpy.run_path(_CANONICAL_APP, run_name="__main__")