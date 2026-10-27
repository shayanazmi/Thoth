# Thoth — Agent Rules (short)

Full rules in `/CLAUDE.md` §8.

1. Only `THOTH.docx` is a spec. Nothing else is behaviourally trusted
   until a `docs/archive/verify/` note confirms it.
2. No pushes to GitHub. Owner handles remote git.
3. No secrets in code or logs. `.env.example` stays current with empty
   values. Route provider error strings through `sanitize_log_message`.
4. Preserve history. Use `git mv`. Move suspect code to
   `docs/archive/legacy_code/<phase>/` rather than deleting until the
   owner approves.
5. Verify before claiming. Running output > a passing test > a status doc.
6. Pydantic v2 for domain and transport. Fail-open on Redis / Supabase /
   LLM providers / scholarly APIs.
7. SQLite schema and Postgres migrations move together.
8. Approval gating is non-negotiable. No test-only bypasses.
9. Never fabricate citations, screening counts, methods, results,
   originality verdicts, or completed activities. Honest
   "insufficiently assessed" is always acceptable.
10. **One phase in flight at a time.** Finish → scenario green →
    walkthrough recorded → commit → next.
11. **Every phase ends with a user-seat walkthrough** in
    `docs/archive/verify/phase_N.md` and a scenario test in
    `backend/tests/scenarios/test_sN_*.py`.
12. **Do not revive the deleted mock-heavy test suites** under
    `backend/tests/`. The scenarios directory is the honest replacement.
