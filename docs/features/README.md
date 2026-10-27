# docs/features: the redesign, one file per feature

Written 24–25 Oct 2026 from the owner interviews. These are the specs; whether each is built, and the
walkthrough that proves it, is tracked in [`docs/SYSTEM_STATE.md`](../SYSTEM_STATE.md).
Start with [00-overview](00-overview.md). Every agent prompt is in [09](09-agents-and-prompts.md).

| # | Feature | Built? | Walkthrough |
|---|---|---|---|
| 00 | [Overview, decisions, pushbacks, build order](00-overview.md) | — | — |
| 01 | [Conversation core (conductor)](01-conversation-core.md) | Yes | [conversation_core](../archive/verify/conversation_core.md) |
| 02 | [Threads, projects, living research file](02-threads-projects-notebook.md) | Partly (notebook proposals; state still client-side) | [conversation_core](../archive/verify/conversation_core.md) |
| 03 | [Thinkers (co-authors)](03-thinkers.md) | Yes | [thinkers](../archive/verify/thinkers.md) |
| 04 | [Hypothesis](04-hypothesis.md) | Yes (client-side versions) | — |
| 05 | [Literature: finding and reading papers](05-literature.md) | Yes, incl. systematic review | [trial](../archive/verify/trial.md) · [systematic_review](../archive/verify/systematic_review.md) |
| 06 | [The trial ("Check")](06-trial.md) | Yes | [trial](../archive/verify/trial.md) |
| 07 | [Study design](07-study-design.md) | Yes | [study_design](../archive/verify/study_design.md) |
| 08 | [Writing: research proposal](08-writing.md) | Yes | [proposal](../archive/verify/proposal.md) |
| 09 | [Agents, methods, models, prompts](09-agents-and-prompts.md) | Reference | — |
| 10 | [UI revamp: the Folio](10-ui-revamp.md) | Yes (plus Obsidian & Gold, motion, intro) | [demo_tour](../archive/verify/demo_tour.md) |
| — | [Thinker roster decision](thinker-roster.md) · [Mind dossiers](../../backend/thinkers/dossiers/) | | |
