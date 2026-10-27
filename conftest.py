"""Repo-root pytest config: keep the scenario gate offline.

pytest loads this file before it imports the ``backend`` package. That order matters:
``backend/__init__.py`` imports ``backend.agents``, whose ``load_dotenv()`` would otherwise
read real provider keys and the hosted Redis/Supabase URLs from ``.env``. The pipeline
scenarios then made live LLM, web-search and Redis calls (~5 minutes per approval test).
``load_dotenv()`` never overrides a variable that is already set, so blanking them here wins.

Set THOTH_LIVE_TESTS=1 to run against the real services.
"""
import os

if os.environ.get("THOTH_LIVE_TESTS") != "1":
    for _k in ("NVIDIA_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "TAVILY_API_KEY",
               "REDIS_URL", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY",
               "SUPABASE_JWT_SECRET", "CONFIDENT_API_KEY"):
        os.environ[_k] = ""
