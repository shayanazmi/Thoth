# Thoth redesign: overview

> Status: **built** (see `docs/SYSTEM_STATE.md` for what's done and open). Written 24 Oct 2026 from the owner interview.
> Trust order: `THOTH/THOTH.docx` > `CLAUDE.md` > these files > everything else.
> Each feature file says what the owner wants, where I disagree, the architecture,
> the agents and prompts it uses, and the user-seat walkthrough that proves it.

## Why redesign

Read from the code on 24 Oct 2026, not from docs:

| Flaw | Where | Effect on the user |
|---|---|---|
| Chat has no memory | `backend/agents.py` `direct_chat_prompt` takes only `{user_query}` | Thoth forgets what was said two messages ago |
| Every non-casual message becomes a plan | `backend/api/routes_chat.py` `_classify_turn` falls through to `RESEARCH_INTENT` | Stray plan cards when the user just wanted to think aloud |
| One output shape for everything | `writer_prompt` always writes Intro / Key Findings / Gaps / Methodology / Conclusion | Scan, review and draft blur into one blob |
| Writer, critic and follow-ups grade their own work | `critic_chain` scores the writer's report out of 10 on the same model | No independent check; Feynman-style separation missing |
| Each thinker exists in 3-4 incompatible forms | `frameworks/*/framework.py` (JSON auditor, "no persona roleplay"), `sparring.py` (same 3-phase script for all), `/api/brainstorm/council` (one call plays all ten) | Personas drift and sound alike |
| Every agent runs on a small model | `nvidia/nemotron-3.5-lightning-30b-a3b` everywhere | Flat voices, shallow reasoning |

The owner's diagnosis, in their words: it is "foundationally illogical" when used the way
a person who walked into a chatbot would use it.

## The product in one paragraph

Thoth looks and behaves like a normal chat. As an idea firms up, a **living research file**
fills in beside it: question → hypothesis → library → trial (synthesis matrix + verdict) →
study design → proposal. Each section updates on its own and is never mashed into one report.
Thoth **suggests** the next step; the user decides. Ten **thinkers** act as co-authors with
their own minds. Every heavy step can run on **Autopilot** or **Co-pilot** (human in the loop).
Big runs show a time and scope estimate first, then fill in visibly while they run.

## Feature files

| # | File | What it covers |
|---|---|---|
| 01 | [conversation-core](01-conversation-core.md) | The conductor, memory, turn handling, reply style, autopilot |
| 02 | [threads-projects-notebook](02-threads-projects-notebook.md) | Thread → Project promotion, the living research file, retention |
| 03 | [thinkers](03-thinkers.md) | Co-authors, mind dossiers, reviews, debates, roster research |
| 04 | [hypothesis](04-hypothesis.md) | Entry bar, sub-claims, rivals |
| 05 | [literature](05-literature.md) | Quick look / scan / systematic review, full paper records, PRISMA |
| 06 | [trial](06-trial.md) | "Check": the hypothesis on trial, synthesis matrix, verdict, originality |
| 07 | [study-design](07-study-design.md) | Design + feasibility stage |
| 08 | [writing](08-writing.md) | Research proposal: outline → sections → verifier → reviewer → thinkers |
| 09 | [agents-and-prompts](09-agents-and-prompts.md) | Roster, method grounding, model map, every draft prompt, drift tests |

## Decisions from the interview (24 Oct 2026)

| Topic | Decision |
|---|---|
| First feel | Chat that grows a notebook |
| Core object | A living research file with separate sections |
| First reply | Brief answer (marked unchecked) + one sharpening question |
| Facts in chat | Allowed, visibly labelled "general knowledge, not yet checked", with one-tap check |
| Who drives | Thoth suggests, user decides |
| Research cue | Offered only when the idea is specific enough, at most once until answered |
| Memory | Whole project (summarised when long) |
| Turn brain | One conductor with tools; heavy actions are only offered |
| Notebook writes | Proposed, one tap to accept, versions kept |
| Projects | A thread is promoted to a Project when a hypothesis is accepted |
| Reply length | Adaptive |
| Thinkers | Co-authors with distinct minds; all 10 visible; roster researched → [thinker-roster.md](thinker-roster.md), [dossiers](../../backend/thinkers/dossiers/) |
| Thinker reviews | Independent (separate calls, unseen by each other); debates are sequential |
| Literature | Three tiers; every paper gets a full record, not just title + abstract |
| Check | Neutral trial; synthesis matrix; verdict can go against the hypothesis |
| Auto vs human | One project switch (Autopilot / Co-pilot) + per-step override |
| Draft | A research proposal, written outline-first, section by section |
| Draft gates | Verifier + Reviewer + Thinker reviews before "reviewed" |
| Study design | A separate stage before the draft |
| Models | Free NVIDIA NIM only; strong model for key roles |
| Deletion | Deleting a project deletes everything (after confirmation) |
| Big runs | Time + scope estimate, then a live view of the work |
| Build first | Conversation core + notebook (owner left it to me) |

## Where I pushed back (and what we agreed)

1. **Project only at hypothesis.** The notebook fills before a hypothesis exists, so that
   work needs a home → threads that get promoted (agreed).
2. **Prosecutorial trial.** It invites motivated reasoning and manufactured gaps (forbidden by
   vision §11) → neutral court that can convict (agreed).
3. **Strategic stance "pivoting"** can launder weak evidence into a gap. It stays, but the
   Judge must show the evidence that justifies it, or it is refused.
4. **Matrix needs full text.** Paywalled papers get "not reported in abstract", never a guess,
   and a lower witness weight (agreed).
5. **Hypothesis bar = named variables only.** It's fine as an entry bar, but without a falsifier the
   trial cannot convict, so a missing falsifier is flagged as a weakness (not a blocker).
6. **All 10 thinkers independently = 10 model calls.** That's acceptable only when the user asks for
   a full council review; the default is Thoth suggesting the one or two most relevant thinkers.

## Ideas borrowed from other research agents

Feynman (read from the local install, `@companion-ai/feynman` 0.3.3):
- one job per agent (researcher / writer / verifier / reviewer);
- the writer never adds citations, the verifier does it as a separate pass and checks meaning, not topic overlap;
- FATAL / MAJOR / MINOR review with "fix FATAL before delivery";
- durable artefacts per run (plan, draft, cited, provenance) and `Verification: BLOCKED` instead of pretending;
- a scale decision: a narrow question never becomes a multi-agent survey.

Other systems (from my knowledge; not re-verified this session):
- **LangChain Open Deep Research**: clarify → brief → supervisor + researchers → report. Same stack as Thoth.
- **Stanford STORM**: perspective-guided questions, then outline-first writing.
- **PaperQA2**: agentic retrieval over full text, contradiction detection.
- **Elicit**: per-paper extraction tables, the nearest product to our synthesis matrix.
- **Google AI co-scientist**: generate → debate → evolve hypotheses, ranked by tournament.
- **Sakana AI Scientist**: novelty check against Semantic Scholar before pursuing an idea.

## Build order

1. 01 + 02: conversation core and notebook. Everything else plugs into it.
2. 05 + 06: Librarian/Reader/Analyst/Judge and the trial matrix. This is the heart of the demo.
3. 03: thinkers (roster and dossiers drafted 24 Oct; owner to approve the four swaps).
4. 04, 07, 08: hypothesis tooling, design, proposal writing.

Each step ends with a scenario test in `backend/tests/scenarios/` and a walkthrough in
`docs/archive/verify/`, per `CLAUDE.md`.

## What retires

- `_classify_turn`'s six fixed paths are replaced by the conductor (01).
- `writer_prompt`'s fixed five sections are replaced by tier-specific outputs (05, 06, 08).
- `critic_chain` is replaced by the Reviewer (08). The self-score out of 10 goes.
- `sparring.py`'s shared 3-phase script and the one-call council are replaced by per-thinker dossiers (03).
- The mind-map chains are frozen (not on the journey). They come back later as a view over the matrix, if wanted.

Retired code moves to `docs/archive/legacy_code/redesign_v3/`; nothing is deleted.
