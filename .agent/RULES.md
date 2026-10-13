# 📜 Agent Rules & Constraints for Thoth

## 1. Ground Rules & Safety
1. **GitHub is Off-Limits for the Agent:**
   - Only the human developer touches remote GitHub (`git push`, pull requests, remote branches).
   - If git assistance is requested, provide clear CLI instructions and ask for confirmation before executing any local git commands.
2. **Zero Secrets in Code or Logs:**
   - Never print, hardcode, or commit secrets (`.env`, `SUPABASE_SERVICE_ROLE_KEY`, `NVIDIA_API_KEY`, etc.).
   - Keep `.env` and `vault/` in `.gitignore`. Maintain `.env.example` with updated variable keys (empty values).
3. **Never Delete Without Explicit Approval:**
   - Use `git mv` to preserve commit history.
   - Move uncertain or legacy items to `archive/`.
4. **Ignore Virtual Environments and Caches:**
   - Never touch `venv/`, `__pycache__/`, `.pytest_cache/`, or `.deepeval/`.
5. **Phase-by-Phase Discipline:**
   - Work strictly in the specified order: 1) Docs → 2) Web → 3) Backend → 4) Scripts.
   - Do not begin the next phase until the current phase is tested, committed, and approved.
6. **Sequential Problem-Solving:**
   - Think sequentially through complex problems.
   - When requirements are ambiguous, prompt the developer with `/grill-me` or interactive questions.

## 2. Coding & Architecture Standards
1. **Pydantic v2 & Type Hinting:**
   - All domain schemas and request/response contracts must be strictly validated.
2. **Fail-Open Resilience:**
   - If Redis or an external service drops, fallback to in-memory caches or direct requests without crashing the research session.
3. **Test Suite Integrity:**
   - Run `pytest` after making modifications to ensure no regressions across the 360 test suite.
