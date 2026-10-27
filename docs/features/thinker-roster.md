# Thinker roster

> 24 Oct 2026. **Approved by the owner on 24 Oct 2026** (all four swaps). The code still has the old ten;
> the swap lands when feature 03 is built.

## Criteria (agreed in the interview)

1. **Distinct minds.** No two thinkers who would say the same thing about the same idea.
2. **Beyond the Western canon.**
3. **Social and human sciences included**, not only physics and biology. Most user questions will be about people.
4. **Well-documented minds.** Enough of their own writing survives to model how they thought, not just what they concluded.

Plus one practical test: **does this thinker earn a place on the journey?** Each must bring something to
at least one stage (shape the idea, stress-test the hypothesis, critique evidence, design the study)
that no one else on the roster brings.

## Recommendation: 10 thinkers

| # | Thinker | Status | What only they bring | Strongest stage |
|---|---|---|---|---|
| 1 | **Aristotle** | keep | What *is* the thing? Definitions, kinds, and four kinds of explanation; starting from what people already believe | shaping the idea |
| 2 | **Ibn al-Haytham** | **add** (replaces Bacon) | Doubt towards authorities, including the most revered; checking claims by controlled, repeatable test | stress-test, design |
| 3 | **David Hume** | keep | What do we actually observe, and what are we adding? Causation, induction, belief in proportion to evidence | stress-test |
| 4 | **Charles Darwin** | keep | Patient accumulation; mechanisms that explain variation; a notebook of facts against your own view | shaping the idea, evidence |
| 5 | **Florence Nightingale** | **add** (replaces Box) | Numbers as moral instruments; comparing like with like; turning data into reform | evidence, design |
| 6 | **Max Weber** | **add** (replaces Descartes) | Meaning: why people act as they do, in their own terms; ideal types; many causes, not one | shaping the idea, evidence |
| 7 | **Karl Popper** | keep | What would show you wrong? Bold conjectures and severe tests | stress-test |
| 8 | **Thomas Kuhn** | keep | Which paradigm are you inside, and what does it stop you seeing? Anomalies; how communities decide | evidence, gap |
| 9 | **Herbert Simon** | keep | Real people and organisations decide with limited information; satisficing; designing for how things actually work | design |
| 10 | **Elinor Ostrom** | **add** (replaces Turing) | Field evidence against tidy models; institutions people build for themselves; no panaceas | evidence, design |

Dossiers: [`backend/thinkers/dossiers/`](../../backend/thinkers/dossiers/).

## Why these swaps

**Bacon → Ibn al-Haytham.** Both stand for testing claims by experiment, so keeping both would break
criterion 1. Ibn al-Haytham did it six centuries earlier, documented his experiments in detail in the
*Book of Optics*, and wrote a whole book (*Doubts concerning Ptolemy*) about how a seeker after truth
must suspect even the authorities he admires. That meets criterion 2 and is the stronger voice. What we
lose from Bacon, his "idols" (systematic biases of mind), is partly covered by Hume and Kuhn, and the
Reviewer checks for bias anyway.

**Box → Nightingale.** Both bring statistical thinking. Box's voice ("all models are wrong") is narrow
and survives mostly as aphorisms. Nightingale left a huge documented record (letters, reports,
statistical diagrams), argued from comparative mortality data to change institutions, and is directly
relevant to health and nursing questions, which is the demo topic. Criteria 3 and 4.

**Descartes → Weber.** Descartes's rationalist decomposition overlaps with Aristotle's conceptual
analysis, and nobody on the old roster asked *what an action means to the people doing it*. Weber's
interpretive method, ideal types and insistence on multiple causes are the most distinct addition
available for social research. Criteria 1 and 3.

**Turing → Ostrom.** Turing is a brilliant, well-documented mind, but his territory (computation,
formal systems) is far from most research questions Thoth will see, so he'd mostly say "not my
territory". Ostrom brings field, laboratory and comparative-case evidence against elegant models,
grounded in how real communities solve problems. Criterion 3, plus the journey test.

## Bench (kept documented, not on the default roster)

| Thinker | Why benched | When to bring back |
|---|---|---|
| Francis Bacon | Overlaps with Ibn al-Haytham | A user wants the "idols" lens explicitly |
| René Descartes | Overlaps with Aristotle | Philosophy-of-mind or foundations topics |
| George Box | Narrow, aphoristic record | Statistical modelling projects |
| Alan Turing | Territory too narrow for most questions | AI and computation projects |
| W. E. B. Du Bois | Strong candidate; overlaps partly with Weber (both empirical social science, 1890s-1900s) | First choice to add if the roster grows to 11, or to swap for Weber on questions about race and inequality |
| al-Biruni | Overlaps with Ibn al-Haytham (empirical method, same era) | Comparative or measurement-heavy topics |
| Barbara McClintock | Less of her own reasoning is in print | Genetics projects |
| Richard Feynman | Overlaps with Popper and Hume (honesty, self-deception) | Physics projects |

A later feature could let users swap a bench thinker in per project. The current design (03) keeps the
roster fixed at ten.

## Diversity check

Traditions: Greek, medieval Islamic, Scottish Enlightenment, Victorian British (×2), German, Austrian,
American (×3). Women: 2 of 10. Disciplines: philosophy (3), natural science (2), statistics and public
health (1), sociology (1), history and philosophy of science (1), cognitive science and economics (1),
political economy (1). Still weighted towards European men; Du Bois and al-Biruni are the first
candidates if the owner wants to push further.

## Impact on code (when built)

- `backend/intellectual_rigour/thinkers.yaml`: 4 entries swapped. Benched entries get `status: bench`.
- `frameworks/<id>/`: replaced by `backend/thinkers/dossiers/<id>.md` (03). Benched frameworks move to
  `docs/archive/legacy_code/redesign_v3/`.
- Frontend bust initials and the council layout pick up the new names automatically from the API.
