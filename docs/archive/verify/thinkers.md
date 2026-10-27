# Thinkers as co-authors: user-seat walkthrough (24 Oct 2026)

Feature: `docs/features/03-thinkers.md`. Roster approved by the owner on 24 Oct 2026.
Live NVIDIA NIM (`nemotron-3-ultra-550b-a55b`), in-app browser on :8000, the night-shift nurses project.

## What was built

- `backend/thinkers/`: `dossiers/*.md` (single source of truth per persona), `roster.py` (approved ten,
  territories, profiles), `persona.py` (doc-09 persona prompt + support prompts), `modes.py` (join, room,
  independent review, council, sequential debate, co-author memory, concurrency cap).
- `thinker_memory` table (SQLite + `db/migrations/007_thinker_memory.sql`).
- `/api/thinkers` router; `/api/brainstorm/{thinkers,chat,council}` now delegate to it. The shared
  `sparring.py` script and the one-call council are no longer on any user-facing path.
- Conductor suggestions use dossier territories; thinker turns in the main chat are stored in the
  thread, so Thoth sees what a thinker said (closes a gap from the conversation-core walkthrough).
- Frontend: reviews card with verdicts, clickable busts → profile, streamed debates, 2-3 debaters,
  room memory, "Get reviews" on the hypothesis card.

## Walkthrough

| # | Did | Saw | Verdict |
|---|---|---|---|
| 1 | Get reviews on the hypothesis | Popper, Hume and Nightingale reviews, each in their own voice ("What does it forbid?" / constant conjunction / "first, the comparison"); verdict badges mixed · mixed · objecting (2 critical) | pass (after fix 2) |
| 2 | Tap Popper's bust | Profile from the dossier: life, cared about, how his thinking moved, blind spots, sources | pass (after fix 3) |
| 3 | `/debate popper kuhn …` | 3 rounds, sequential, each answering the others with real concessions; Thoth's distillation; hypothesis offered as a proposal only | pass (after fixes 4-6) |
| 4 | Open Thinkers stage | New roster of ten with years and "what they bring" | pass (after fix 7) |
| 5 | Council (triggered by bug, see 7) | 10 independent takes in ~20s, all served by Ultra, no rate-limit fallbacks | pass |

## Problems found and fixed

1. **Rate limits**: 10 parallel calls hit NIM 429s and silently fell back to another model. Thinker calls are
   now capped at 4 concurrent.
2. **Review envelopes empty**: 500-token budget truncated the JSON. Raised to 1500; memory updates moved to
   the background so reviews return sooner (~40s for three).
3. **Profile text**: hard wraps rendered as line breaks; the dossier's "you" was unexplained. Unwrapped
   server-side; a line now says it is the brief the thinker is given.
4. **`/debate popper kuhn Can a single…`** pulled in Aristotle ("a" matched his name) and dropped "a" from the
   question. Name matching is now id or whole name word of 3+ letters; names are taken only from the front.
5. **Debate hypothesis suggestion** was a 90-word study plan. Distillation now asks for one testable sentence
   (≤35 words); re-run on the same debate gave 15 words.
6. **Example reuse**: Aristotle used the chick-in-the-egg example in all three rounds. Debate mode now says
   not to reuse an example already given in the debate.
7. **Opening the Thinkers stage ran the full council** (10 calls) unasked. Removed; the council runs only on request.
8. Bust initial for "Ibn al-Haytham" showed "a"; now "H".

## Blind attribution (live, `test_s12_thinker_blind_attribution.py`)

| Run | Result | Note |
|---|---|---|
| 1 | void | 429s → fallback model; judge out of tokens |
| 2 | 10/30 | prompt 2 scored 10/10; the judge's 10-way JSON answer failed to parse on prompts 1 and 3 |
| 3 | 22/30 (73%) fail | per-reply judging; Hume, Ibn al-Haytham, Weber drifted into a generic "use both, triangulate" voice |
| 4 | **28/30 (93%) pass** | after the "start where you would start" rule; misses: Ibn al-Haytham → Nightingale, Darwin → Nightingale |

Raw replies and guesses: `_logs/thinker_blind_attribution_2026-10-24*.json`.

## Watch items: handled 24 Oct 2026 (later the same day)

| Item | Fix | Live check |
|---|---|---|
| Contested history stated as fact (Kuhn on Eddington's plates) | Thinker preamble: disputed history must be marked disputed; Kuhn's dossier records the Earman & Glymour (1980) vs Kennefick (2009) dispute | Kuhn now gives both readings and says "historians still argue about it" |
| Ibn al-Haytham the weakest voice | Dossier gains his Book VII refraction instrument as a worked example, and a sharper first instinct: design the check rather than split the difference | Opens "I would put to the test rather than decide by reputation" and designs a comparison |
| Hume's "you know my rule" | Persona forbids announcing doctrines by name or opening replies the same way; Hume's dossier names the tic | No "my rule"; argues through examples (bread, what else comes with night shifts) |
| Pipeline thinker check on old auditors | `intellectual_rigour/thinker_hook.py` rewritten on the co-author engine (Hume for causal questions, Nightingale for health, Popper otherwise); old version archived in `docs/archive/legacy_code/redesign_v3/` | Live: Hume reviewed a placeholder report and said there was nothing to review; S12 tests cover the engine path and the model-down path |

Still open: **no valid blind-attribution score after these fixes yet.**
- v3 run: void (a concurrent trial caused 429s; 12 calls fell back to gpt-oss-20b).
- v4 run, alone: 21/30, but 8 calls still fell back, so also void.
- The test now refuses fallback answers (`get_role_llm(..., allow_fallback=False)`, 2 concurrent calls). Its
  first run stopped on a persistent 429: the free tier was saturated after a day of heavy use.
**25 Oct 2026, valid run (sequential, no fallback answers): 24/30 (80%).** That meets the overall bar but fails the
per-thinker rule: Ibn al-Haytham 1/3 and Darwin 1/3 (misread as Nightingale or Popper); Hume, Nightingale, Weber,
Popper, Kuhn and Ostrom 3/3; Aristotle and Simon 2/3. On the nursing-measurement prompts both slip into the same
textbook confounder checklist (selection, staffing, patient load) before their own moves. Raw:
`_logs/thinker_blind_attribution_2026-10-25.json`. Previous valid score: 28/30 (v2, before these fixes). Re-run with:
`THOTH_LIVE_TESTS=1 venv/bin/python -m pytest backend/tests/scenarios/test_s12_thinker_blind_attribution.py -s`
The extractor's "critical" grading and `sparring.py` / `matcher.py` retirement remain as before.

## Darwin / Ibn al-Haytham fix and re-runs (25 Oct 2026)

Fix: persona rule against opening with the generic confounder checklist; both dossiers gained a written first
instinct (Darwin: variation, natural history over time, selection as a process, ask practitioners; Ibn al-Haytham:
the arranged test, the trusted instrument as an authority to check, perception vs judgement) and a "misreading
to avoid" for the checklist opening.

| Run | Prompts | Score | Darwin | Ibn al-Haytham | Below 2/3 |
|---|---|---|---|---|---|
| before fix | nursing | 24/30 | 1/3 | 1/3 | Darwin, Ibn al-Haytham |
| after fix | nursing | 21/30 | 1/3 | 0/3 | invalid as a measure: 6 of 9 misses went to Nightingale on nursing-only prompts (topic bias) |
| after fix | neutral (bike lanes, pupils' learning, school anxiety) | 23/30 | **3/3** | **2/3** | Aristotle 1/3, Hume 1/3 |

Reading: the two targeted voices now pass on neutral prompts. But which thinkers fall short changes from run to run
(each thinker is judged on only 3 replies), so the test is noisy. Before more tuning, the test needs more prompts
(e.g. 6-9 across domains) to separate real drift from judge variance. Raw files: `_logs/thinker_blind_attribution_2026-10-25*.json`.

## 9-prompt blind attribution (25 Oct 2026): PASS

Prompts: 3 question types × transport / education / work; each thinker judged on 9 replies, one call at a time,
no fallback answers. **77/90 (86%)**, every thinker ≥ 6/9: Hume, Popper, Simon, Ostrom 9/9; Aristotle,
Ibn al-Haytham, Darwin, Nightingale, Kuhn 7/9; Weber 6/9 (the weakest, twice read as Simon). Most misses went to
Simon or Popper, the judge's default for "careful methods" talk. No thinker is consistently weak, so no dossier
changes were made. Raw: `_logs/thinker_blind_attribution_2026-10-25_9prompts.json`.
