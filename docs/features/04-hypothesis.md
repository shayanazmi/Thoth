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
