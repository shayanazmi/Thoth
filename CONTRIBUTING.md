# Contributing to Thoth

Thank you for helping. Thoth is small on purpose: every change should make it more honest, more useful to a
researcher, or simpler.

## Set up

```bash
git clone https://github.com/shayanazmi/Thoth.git && cd Thoth
make setup        # .venv, requirements, .env
make test         # offline scenario tests; no keys needed
make dev          # http://localhost:8000 (add NVIDIA_API_KEY to .env for real runs)
```

## How changes are judged

1. **The vision first.** [docs/VISION.md](docs/VISION.md) is the reference, especially its guardrails (§11).
2. **Seen from the user's seat.** Try the change in the browser, the way a researcher would.
3. **Tested.** A behaviour change comes with a scenario test in `backend/tests/scenarios/`, written as what the
   user would see.
4. **Simple.** The smallest change that solves the problem; no speculative options or layers.

## Code conventions

- Python: Pydantic v2 for domain and transport objects; new model calls through `get_role_llm` /
  `FallbackLLMWrapper`; external services fail open; provider errors through `sanitize_log_message`.
- Schema changes go in `database/schema.sql`.
- Frontend: vanilla ES modules and CSS tokens, no build step; wrap storage access in `try/catch`; respect
  `prefers-reduced-motion`.
- Never fabricate citations, counts, access or results; never upgrade abstract-only reading to full text;
  costly work only behind an explicit approval.

## Thinker dossiers

Corrections to `backend/thinkers/dossiers/` are very welcome. Please cite the source (work and page or
section) for any change.

---

<sub>Thoth · Developed by Shayan Azmi</sub>
