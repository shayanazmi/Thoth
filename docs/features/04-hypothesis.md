# 04 · Hypothesis

> Vision: §3 stage 8 (refine one main hypothesis), §4.1.

## What the owner wants

- The minimum bar to enter the trial: **named variables or constructs** ("night-shift work",
  "burnout").
- **One main hypothesis plus parked rivals**: one is under trial; alternatives wait in a side list and
  can be swapped in.
- Sub-claims are split out automatically (Autopilot) or proposed for approval (Co-pilot).
- Accepting a hypothesis promotes the thread to a Project (02).

## Where I pushed back

Named variables is a fair *entry* bar. But a hypothesis without a stated falsifier ("what result would
show this is wrong?") can't be convicted, so the trial loses its teeth. Agreed handling: the
hypothesis card shows four strength markers, and a missing one is a visible **weakness**, not a blocker:

| Marker | Example | Required? |
|---|---|---|
| Named constructs | night-shift work; burnout (MBI emotional exhaustion) | **yes** (entry bar) |
| Direction + comparison | higher than day-shift nurses | flagged if missing |
| Population + scope | hospital RNs, EU/US, 2010-2025 | flagged if missing |
| Falsifier | no difference after controlling for workload and sleep | flagged if missing |

The Judge (06) cites missing markers when it explains why a verdict is weak.

## Design

### Card

The current hypothesis is pinned above the chat (already built in UI v2): statement, strength markers,
version history, **Edit**, **Swap with rival**, **Put on trial**.

### Where hypotheses come from

- A conductor `notebook_proposal` during conversation.
- A thinker's review or a debate distillation ("Popper's version: …"). Shown as a proposal, never auto-applied.
- User edits.

Every change bumps the version. A trial is always tied to `hypothesis_version`, so an old verdict is
never shown against a new hypothesis. Stale verdicts are labelled "for v3; hypothesis is now v4".

### Sub-claims

The Analyst splits the hypothesis into 2-5 atomic, testable sub-claims, each one link in the causal or
comparative story. Example for "night-shift nurses burn out more because of sleep disruption":
1. Night-shift work → shorter or poorer sleep.
2. Poorer sleep → higher emotional exhaustion.
3. Night-shift nurses report more burnout than day-shift nurses.
4. The night-shift effect is partly or fully explained by sleep (mediation).

These become the matrix columns (06). Co-pilot: proposed with Accept / Edit. Autopilot: set directly,
editable later; edits invalidate affected matrix cells.

### Rivals

`hypotheses(project_id, id, statement, markers_json, status: main|parked|retired, version)`.
Swapping a rival in keeps the library and the Reader's neutral paper records (05), so only the
Analyst's mapping reruns. That's one reason the Reader is hypothesis-blind.

## Prompt

Sub-claim splitting is part of the Analyst prompt: [09 § Analyst](09-agents-and-prompts.md#analyst).

## Walkthrough (acceptance)

1. Accept a hypothesis with no falsifier → the card shows "falsifier missing" as a weakness, and **Put on trial** still works.
2. Co-pilot: sub-claims are proposed; edit one; the matrix columns match.
3. Park a rival, swap it in → the library is reused, only the mapping reruns, and the old verdict is labelled stale.

Scenario test: `test_s13_hypothesis_versions_and_rivals.py`.

## Build note (27 Oct 2026)

Built: strength markers (`backend/research/hypothesis.py`, cached per version in the notebook), rivals on the
server with park / retire / swap (`backend/conversation/projects.py`), trials tied to `hypothesis_version` with a
stale label, and re-mapping a finished trial's library to the current hypothesis (`trial.remap_plan`; runs on
approval, no search, no Reader). Migration `011_trial_hypothesis_version.sql`. Frontend `frontend/js/hypothesis.js`.
Walkthrough: `docs/archive/verify/hypothesis.md`. Scenario: `test_s13_hypothesis_versions_and_rivals.py`.

Departures: rivals are notebook versions (`rival_hypothesis` + `rivals_retired`), not a `hypotheses` table; the
entry bar is two named constructs (vague placeholders rejected), stricter than "named constructs", after
"Things just get worse at night" passed with one; a scope must add words beyond the constructs and the
comparison. Old trials get their version inferred from their text. Not yet: the Judge is not given the markers,
and the Writer and Designer don't check the trial's version.


## Build note (29 Oct 2026): why each version changed

Every version of the question, the hypothesis, a rival or the design stores a rationale with it, write-once
(`notebook_sections.rationale_json`, `backend/memory/rationale.py`):
- `reason` and `trigger`: initial, your edit, Thoth's proposal, a rival swap, an idea, a thinker, a design revision;
- `evidence` given for it, and `decision_ref` (the proposal or finding it came from);
- `context` attached by the server: what was known then, e.g. the latest trial verdict for the version replaced. It is never presented as the reason;
- `previous_version`.

Editing asks "Why are you changing it?" (optional). `GET /api/projects/{id}/history?kind=` returns every version and
the original motivation with its question. The Writer gets `hypothesis_history` and `design_history`.
Tests: S25. Walkthrough: `docs/archive/verify/revision_history_and_design_loop.md`.
