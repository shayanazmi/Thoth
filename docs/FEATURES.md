# Thoth features

What Thoth does, stage by stage. Section numbers are referenced from the code (`docs/FEATURES.md §N`).
The journey is **Explore → Thinkers → Hypothesis → Check → Review → Design → Draft**; you can move back and
forth freely, and nothing costly runs without your approval.

| § | Feature | Code |
|---|---|---|
| 1 | [The conversation](#1-the-conversation) | `backend/conversation/conductor.py`, `frontend/js/chat.js` |
| 2 | [Threads, projects and the research file](#2-threads-projects-and-the-research-file) | `backend/conversation/projects.py`, `backend/memory/` |
| 3 | [The thinkers](#3-the-thinkers) | `backend/thinkers/`, `frontend/js/thinkers.js` |
| 4 | [The hypothesis](#4-the-hypothesis) | `backend/research/hypothesis.py`, `frontend/js/hypothesis.js` |
| 5 | [Literature](#5-literature) | `backend/research/librarian.py`, `reader.py`, `appraisal.py`, `citations.py`, `review.py` |
| 6 | [The trial](#6-the-trial) | `backend/research/trial.py`, `analyst.py`, `judge.py`, `frontend/js/trial.js` |
| 7 | [Study design](#7-study-design) | `backend/research/designer.py`, `frontend/js/design.js` |
| 8 | [Writing the proposal](#8-writing-the-proposal) | `backend/research/writer.py`, `verifier.py`, `reviewer.py`, `proposal.py` |
| 9 | [Agents and models](#9-agents-and-models) | `backend/agents.py`, `backend/research/llm.py` |
| 10 | [The interface](#10-the-interface) | `frontend/` |

---

## 1. The conversation

One conversation, like a normal chat. Each turn goes to the **conductor**, a single agent with tools:

- It answers briefly and asks one sharpening question. General-knowledge statements are marked with a
  dotted underline and a **check** button that looks the claim up in the literature.
- It remembers the whole project: recent turns verbatim, older ones as a rolling summary, plus what each
  thinker has said in the council and in one-to-one rooms (labelled as opinion, not evidence).
- It can **propose** (never write) changes to the research file, **suggest** a thinker, or **offer** a
  heavier step (a trial or a systematic review) with its estimated cost. You accept, edit or dismiss.
- It never starts heavy work by itself. The chat never blocks: you can keep talking while a trial or a
  review runs.
- A quotation attributed to someone (a thinker, an author) is checked against the record; words that are not
  in it are flagged as a paraphrase.
- An idea is kept only when you explicitly keep it.

Slash commands: `/brainstorm`, `/council`, `/debate popper kuhn`, `/room hume`, `/hypothesis …`, `/check`,
`/review`, `/draft`.

## 2. Threads, projects and the research file

- Every conversation starts as a **thread**. It becomes a **project** when you accept a hypothesis.
- Beside the chat, a **living research file** fills in: where it started, ideas, the question, the
  hypothesis (with versions and rivals), the trial, the review, the design and the proposal. Each section
  is separate and is never merged into one blob.
- Every version records **why it changed**: the reason, what triggered it (your edit, a trial verdict, a
  thinker's critique, a rival swapped in), the evidence, and what was known at the time.
- **Autopilot / Co-pilot**: one project switch, with per-step overrides for sub-claims, screening and the
  proposal. Co-pilot stops for your confirmation at each of those steps; Autopilot carries on. Approval
  gates for costly work apply in both modes.
- **Live work**: a running trial shows papers found and analysed and model calls used, and can be
  **stopped**; the work done so far is kept.
- **Deleting** a project removes everything it holds, after a confirmation that lists the counts. There is
  no global library.
- Project state lives on the server (SQLite), so a second browser rebuilds the same project.

## 3. The thinkers

Ten historical thinkers act as co-authors with their own minds (see [THINKERS.md](THINKERS.md)). Each is
driven by a **dossier** (`backend/thinkers/dossiers/`) written in the second person: life and problems,
what they cared about, worked examples of how their thinking moved, temperament, commitments, blind spots,
misreadings to avoid, territory and sources.

- **Council**: every thinker gives a first reaction, each in a separate call, without seeing the others.
- **Debate**: two or three thinkers argue in turn about your idea.
- **One-to-one room**: talk with one thinker alone; Thoth hears what was said there.
- **Reviews**: independent reviews of your hypothesis or proposal.
- Thinkers remember the project and can change their minds, and the change is shown.
- They criticise with severity, but **no thinker has a veto**. A thinker outside their territory says so.

## 4. The hypothesis

- One working hypothesis at a time; every edit becomes a new **version**, with its reason.
- **Strength markers**, checked once per version: named constructs (at least two things that vary, required
  before a trial), direction, scope and a falsifier. Missing ones are weaknesses, not blockers.
- **Rivals** are parked on the server; you can retire one or swap it in (the old main hypothesis becomes a
  rival). A swapped-in rival can **re-map** an existing trial's library instead of searching again.
- Each trial is tied to the hypothesis version it tested.

## 5. Literature

**Search.** OpenAlex, Europe PMC and Semantic Scholar, with relevance ranking, cursor paging, de-duplication
by DOI and other identifiers, and a log of every request as made. Anonymous access works; API keys raise
the limits.

**Full text.** Legally accessible open-access versions are retrieved where possible. Every paper is labelled
**full text** or **abstract only**, and that label is never upgraded. You can add a paper by DOI or upload a
PDF.

**Paper records.** Each paper is read neutrally (without seeing your hypothesis) into a record with
provenance: question, design, sample, measures, findings, limitations, and what the authors claim beyond
their evidence.

**Appraisal.** Each study is appraised with a checklist for its design: Cochrane RoB 2 domains for
randomised trials; JBI checklists for quasi-experimental, cohort, case-control, analytical cross-sectional,
qualitative studies and systematic reviews; core questions otherwise. A paper's weight combines design,
access and appraisal.

**Citations.** The strongest papers' citation neighbours (citing and cited works) are checked for prior work
that would undermine an originality claim.

**Systematic review (PRISMA 2020).**
1. A **protocol** first (question, eligibility criteria, databases, search strings) that you edit and approve.
2. A **budget** with an estimate of time and cost; **Auto** or **Human-in-the-loop** screening.
3. Identification, title/abstract and full-text screening (screen on what was studied, never on what was
   found), citation rounds, and full-text retrieval.
4. Every count in the **PRISMA flow** comes from a recorded decision. Low-confidence decisions are queued for
   you to audit; you can override any of them.
5. **Stopping rules** are recorded: database exhausted, budget reached, screening stopped after many
   consecutive irrelevant records, citations saturated, full-text budget used, a database error, or you.
   You can **Stop** and **Continue**.
6. A summary first (found, screened, included, why it stopped), then limitations in plain words. Reaching
   a stopping rule never claims that nothing else exists.

## 6. The trial

The hypothesis on trial before a **neutral court**:

1. **Plan**: the hypothesis is split into the claims it is made of (you can edit them), with the effort shown
   up front: papers, full texts, time and model calls. Nothing runs until you approve.
2. **Witnesses**: papers are found and read; each becomes a row in the **synthesis matrix**, read against
   each claim.
3. **The ruling**: for each claim and overall, the strongest case **for** and the strongest case **against**,
   with GRADE-style certainty (rated down for risk of bias, inconsistency, indirectness, imprecision and
   abstract-only evidence). Five outcomes: *contradicted*, *contested*, *insufficient evidence*,
   *supported within limits*, *already established*. The ruling can go against you.
4. **Originality**: *likely novel*, *partial overlap*, *substantially covered* or *insufficiently assessed*.
   "Likely novel" is only allowed when an adjacent-field search and the citation check ran and found no
   substantive overlap.
5. **Gaps**: only gaps that specific witnesses reveal, phrased as gaps in this sample, never invented.

Code-level guardrails lower a verdict when most witnesses were read from abstracts only, and keep every
reason in plain words.

## 7. Study design

You give your real resources (time, access to participants, budget, skills, ethics route, tools). Thoth
proposes **candidate designs** fitted to them, each with what it can and cannot conclude, its measures,
sample, analysis and threats to validity. Unsourced claims are flagged. You choose one (with notes); it
becomes the Design section of the research file, versioned. When the peer Reviewer finds a design-level
fatal flaw in the proposal, the design **revises itself**, and you choose again.

## 8. Writing the proposal

1. An **outline** from your research file (title and abstract, background, literature review, gap and
   contribution, question and hypothesis, methods, expected outcomes, limitations and ethics, timeline,
   references). You reorder, add or drop sections, then approve.
2. Each section is **written** from your trial, design and your own words.
3. A **Verifier** checks every claim against the cited passages; unsupported claims are softened or flagged,
   never silently deleted. References are built from the witnesses actually cited.
4. A **peer Reviewer** reads the whole proposal; fatal findings go round the loop (revise, choose, bring the
   proposal up to date, review again), and resolved findings are recorded.
5. **Thinker reviews**, independent of each other.
6. Status stays **Provisional** while anything material is open, with the open items listed.
7. **Export** asks first, and a provisional draft carries a **PROVISIONAL** watermark.

## 9. Agents and models

Every model call goes through `get_role_llm(role)` in `backend/agents.py`: a per-role model map on free
**NVIDIA NIM** models (Nemotron 3 Ultra for every role), falling back to Nemotron 3.5 Lightning on NIM, then
**Groq** (or **OpenAI** without a Groq key), through `FallbackLLMWrapper`. Output from a fallback model is
labelled. Roles include the conductor, the reader, analyst and judge of the trial, the screener of the
systematic review, the designer, and the writer, verifier and reviewer of the proposal. Chain-of-thought is
stripped from replies, and JSON answers are parsed defensively.

**Thinkers speak through models from different labs** (`get_thinker_llm`, `THINKER_ASSIGNMENT`), so the
council does not share one model's blind spots: MiniMax (Popper, Aristotle, Simon), Meta (Hume, Kuhn,
Ibn al-Haytham), OpenAI gpt-oss on Groq (Nightingale, Weber) and Qwen on Groq (Darwin, Ostrom). Thinkers who
argue are on different models, and none is on an NVIDIA model, so the Ultra judge never grades its own
model's thinkers. A thinker whose model fails speaks through a spare from a lab no other thinker uses
(StepFun), never another thinker's model. Their memory notes, review envelopes and debate summaries stay on
Ultra.

**Concurrency** is capped per model (4 calls) and across NIM (8), because the free tier answers 429 to
bursts. Groq allows 8K tokens a minute per model, so it carries at most two thinkers per model.

Chosen from live tests on 2026-11-04. At that time Nemotron 3 Super's free endpoint was deprecated, Kimi K2.6
had been removed, and DeepSeek V4.1, GLM 5.3, Mistral Large 4 and gpt-oss-20b on NIM did not answer reliably.
The NIM model list (`/v1/models`) still names withdrawn models, so check a model with a live call before
assigning it.

## 10. The interface

Vanilla ES modules and CSS, no build step (`frontend/`).

- **Folio layout**: projects sidebar, the conversation with the journey stepper on top, and the research
  file beside it. Chat, Split and File layouts; a phone layout with a bottom bar.
- **Obsidian & Gold** palette (dark by default) and a papyrus light theme, from CSS tokens.
- **Motion**: scene transitions, once-only entrances and a ruling ceremony; all of it respects
  `prefers-reduced-motion`.
- **Cinematic intro**: gold dust forms the mark, the bust appears, and your first question flies into the
  moon. Skippable at any moment.
- **Guided demo** (`frontend/scripted/`, optional): replays a real recorded run as a film, or coaches you
  live against your own backend. See [frontend/scripted/README.md](../frontend/scripted/README.md).

---

<sub>Thoth · Developed by Shayan Azmi</sub>
