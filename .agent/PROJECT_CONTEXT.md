# Thoth — Agent Project Context (pointer)

The authoritative context is `/CLAUDE.md`. Read it first — it is now the
single comprehensive source for any Claude session (Claude Code CLI,
claude.ai, or any other surface) picking up this project.

## One-paragraph summary

Thoth is a research **companion** as defined by `THOTH.docx` (15 Oct 2026,
v1.0). The only trusted spec is `THOTH.docx`. The engine on disk is denser
than the status docs suggested, but the user experience was not vision-
aligned when work began. As of 23 Oct 2026, **Phases 0, 1, and 2 are
complete**: unified `/api/chat/stream` surface, mode UI removed, idea
capture (detect-suggest-promote) landed. **Five of ten vision §3 stages
are closed.** Phase 3 (lightweight scan vs formal PRISMA) is next. Gate:
`make test-vision` → 14/14 passing.

## Required reading, in order

1. `THOTH.docx` — the only trusted spec.
2. `/CLAUDE.md` — primary working context (updated 23 Oct 2026).
3. `docs/archive/verify/BASELINE.md` — honest baseline.
4. `docs/archive/verify/phase_1.md`, `phase_2.md` — what has shipped.
5. `docs/SYSTEM_STATE.md` — current scorecard and next phase.

## Treat as *unverified* (historical only)

- `README.md`
- `docs/roadmap-status.md`
- `THOTH/THOTH_COMPREHENSIVE_ALIGNMENT_AUDIT.md`
- Status claims in docstrings, comments, log lines

## For a fresh Claude Code session

See `/CLAUDE.md` §9 "Quick start for a fresh Claude Code session". The
8-step bootstrap gets you from zero to picking up Phase 3 in roughly 45
minutes.
