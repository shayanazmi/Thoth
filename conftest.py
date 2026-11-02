# Thoth · Developed by Shayan Azmi
"""Keep the test suite offline.

pytest loads this file before the ``backend`` package, and ``load_dotenv()`` never overrides a variable that is
already set, so blanking the provider keys here keeps every test away from live model calls.
Set THOTH_LIVE_TESTS=1 to run the one live-model test against the real services.
"""
import os

if os.environ.get("THOTH_LIVE_TESTS") != "1":
    for _k in ("NVIDIA_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"):
        os.environ[_k] = ""
