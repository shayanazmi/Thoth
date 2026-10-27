# 03 · Thinkers (co-authors)

> **Built 24 Oct 2026**: walkthrough and known gaps in [`docs/archive/verify/thinkers.md`](../archive/verify/thinkers.md).
> Vision: §6 (thinkers), §11 (no single thinker has a veto; philosophical disagreement alone must not
> invalidate a report).

## What the owner wants (their words, condensed)

> A co-author is foundational to research: you discuss every topic, idea and aspect of the work with
> them. Through those discussions you see their reasoning, and so you see where your own reasoning is
> wrong. Each thinker should respond to a subject the way they plausibly would have if they had been
> studying it themselves. This is **not** about a thinker spotting technical flaws or running
> predefined rules. Preserve each thinker's **distinct personality, intellectual character and way of
> thinking**. Each gives their own honest, independent assessment. Don't force agreement.

Further decisions:
- Jobs: shape the idea, stress-test the hypothesis, critique evidence and the draft, and teach the method.
- Voice: in character, in plain modern English. They know they're being consulted now, and never pass
  off post-death events as memories.
- Visible distinctness: voice only in replies; tapping the bust opens a profile.
- Memory: each thinker remembers this project's discussions and can change their mind when shown
  evidence, and says so when they do.
- Reviews are independent (separate calls, unseen by each other); debates are sequential turn-taking.
- Off-topic: they say "not my territory, but…" and give a shorter take, with no faked expertise.
- Roster: keep all 10 visible for now; research which thinkers to keep, using these criteria: beyond the
  Western canon, social and human sciences included, well-documented minds.
- Entry: Thoth suggests the right thinker at the right moment; the user can invite anyone at any time.
- Debate: moderated, three rounds, then Thoth distils it. The user can interject.

## What's wrong today

Each thinker exists in incompatible forms:
1. `frameworks/<id>/framework.py`: a JSON auditor told "NO ARCHAIC PERSONA ROLEPLAY".
2. `sparring.py`: "You are {thinker_name}… philosophical gravity", using the *same* three-phase
   script (diagnose → operationalise → converge) for every thinker. So Darwin behaves like Popper.
3. `/api/brainstorm/council`: one model call writes all ten takes. They blend.
4. The `.md` files (`historical_basis`, `modern_adaptation`, `operational_algo`) feed only sparring.

And all of it runs on a 3B-active-parameter model. Even a strong model gets thinkers wrong without
grounding: on 24 Oct, Ultra's "Popper" claimed one burnout-free nurse would falsify a statistical
claim, which Popper's own treatment of probability statements doesn't support.

## Design

### One source of truth per thinker: the mind dossier

`backend/thinkers/dossiers/<id>.md`, researched and cited, with these sections:

| Section | Purpose |
|---|---|
| Life and problems | What they actually worked on, and why it mattered to them |
| What they cared about | What excited them, what bored them, what they found suspicious |
| How their thinking moved | Characteristic sequences of thought, shown in 3-4 worked examples from their own work (paraphrased, cited) |
| Temperament and voice | How they argued, conceded, joked and dismissed. Plain modern English, no period pastiche |
| Commitments | Positions they held, with sources, and **where scholars think they changed their mind** |
| Blind spots | Known weaknesses and criticisms of their approach (keeps them honest, not idealised) |
| Misreadings to avoid | Common caricatures (e.g. "Popper = one counterexample refutes any claim") |
| Territory | Subjects close to and far from their concerns, used for the off-topic rule |
| Sources | Primary works and key secondary scholarship |

There are no rules or checklists in the persona prompt. The dossier gives the model a mind to
inhabit, and the prompt asks for a *plausible reconstruction* of how that person would engage.

The `framework.py` JSON auditors are retired as personas. Their useful structured output (severity,
claim targeted, suggested test) survives as the **review envelope**: the thinker writes freely in
character, then a cheap extraction step pulls out `{verdict, concerns[{claim, severity, why}],
would_change_mind_if}` for the status logic. Their voice is never forced into JSON.

### Thinker memory (co-author)

`thinker_memory(project_id, thinker_id, stance_summary, positions_json, updated_at)`. After each
exchange, a cheap step updates that thinker's stance: what they believe about this project now, and
what would change their mind. If a position flips, the next reply acknowledges it ("I said X last
time; the cohort data changes my view").

### Modes

| Mode | Calls | Visibility rule |
|---|---|---|
| **Join** (thinker in the main chat) | 1 per reply | Sees the thread + their own memory |
| **Room** (one-on-one) | 1 per reply | Same, in a separate panel |
| **Review** (of hypothesis / matrix / draft) | 1 per thinker, in parallel | **Independent**: sees the artefact and their own memory, never other reviews |
| **Council** (full review by all 10) | 10, only on request, with an estimate | Independent, then an optional discussion round |
| **Debate** | 2-3 thinkers × 3 rounds, sequential | Each sees the debate so far; Thoth moderates and closes with agreements, real disagreements, and what it means for the hypothesis |

Severity gating (vision §6.3): only `critical` concerns can hold a draft at `provisional`, and only
until they are **answered**, not necessarily accepted. No thinker has a veto.

### Suggesting a thinker

The conductor's `suggest_thinker` tool picks from the dossier "Territory" and "What they cared
about" sections, so the match comes from the thinker's concerns rather than a keyword table
(`matcher.py` retires). For example: a causal leap → Hume; a mechanism story → Darwin; definitions
blurring → Aristotle; a measurement or denominator quarrel → Nightingale; institutional rules → Ostrom; what the work means to people → Weber.

### Profile on tap

Rendered from the dossier: portrait, one-line summary, what they cared about, how they reasoned,
blind spots, sources. This also covers the owner's "teach the method" job.

## Roster (researched 24 Oct 2026)

Decision and reasons: [thinker-roster.md](thinker-roster.md). Recommended ten: Aristotle, Ibn al-Haytham,
Hume, Darwin, Nightingale, Weber, Popper, Kuhn, Simon, Ostrom. Bacon, Box, Descartes and Turing move to
the bench, with Du Bois first in line if the roster grows.
Dossiers: [dossiers/](../../backend/thinkers/dossiers/). First live probe: [`docs/archive/verify/redesign_persona_probe.md`](../archive/verify/redesign_persona_probe.md)
(the Popper misreading is fixed; blind attribution 18/18 on one prompt).

## Drift test (agreed: blind attribution)

`backend/tests/scenarios/test_s12_thinker_blind_attribution.py`, with live model calls behind a marker:
1. Give the same three prompts (a causal claim, a definition dispute, a messy dataset) to every thinker.
2. Strip names; a judge model must attribute each reply to a thinker from the roster.
3. Pass: at least 80% correct attribution overall, and no thinker below 60%. A thinker who falls below
   that has drifted, so its dossier needs work.

Plus golden checks per dossier "Misreadings to avoid" (e.g. Popper must not claim a single counterexample
refutes a statistical hypothesis).

## Prompts

Persona template and a worked Popper example: [09 § Thinkers](09-agents-and-prompts.md#thinkers).
Model: Ultra for every thinker call; Lightning for the cheap memory-update and envelope-extraction steps.

## Walkthrough (acceptance)

1. In a chat about night shifts and burnout, Thoth suggests Hume once, on a causal statement. Invite him:
   he speaks as Hume, not as a rule list.
2. Disagree with him and give a reason. Next time he refers back to it, and either holds his view with
   reasons or revises it and says so.
3. Ask for a review of the hypothesis by Hume, Popper and Nightingale: three independent reviews that don't quote each other.
4. Start a debate (Popper and Kuhn): three sequential rounds, each responding to the last, then Thoth's distillation.
5. Tap Aristotle's bust → the profile opens. Ask him about a regression model: "not my territory, but…".
