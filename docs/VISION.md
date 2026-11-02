# Thoth: product vision

> A research companion for discovering questions, developing original ideas, and building defensible knowledge.
>
> Vision brief, version 1.0 (15 October 2026), by **Shayan Azmi**. The original document is
> [`vision/THOTH.docx`](vision/THOTH.docx); this page renders its substance for reading on GitHub.

## The central idea

> Thoth should not merely answer questions a researcher already knows how to ask. It should help people
> discover which questions are worth asking, understand what existing scholarship establishes, and
> investigate what might meaningfully add to that knowledge.

Open-source ambition · Evidence-led · Simple by design

---

## 1. Product north star

Thoth is an open-source research companion that helps people move from curiosity to original, defensible
contributions to knowledge. Unlike conventional research assistants that expect a predefined question and
then retrieve papers to answer it, Thoth supports the entire intellectual journey: discovering research
questions through conversation, exploring ideas, understanding existing scholarship, developing hypotheses,
challenging them, and eventually producing rigorous reports and manuscript drafts.

A user should be able to open Thoth, begin with an observation or an ordinary conversation, and gradually
discover a meaningful research direction without already knowing the exact question to ask.

### Three connected roles

| Role | Purpose |
|---|---|
| Conversational intellectual companion | Supports ordinary conversation, curiosity, interdisciplinary exploration and natural brainstorming without requiring a formal research prompt. |
| Rigorous research investigator | Discovers, reads, compares and critically evaluates literature; investigates contradictions; assesses whether a proposed contribution is genuinely original. |
| Research-development partner | Helps refine hypotheses, design feasible studies, document evidence and develop an evolving manuscript without inventing results or overstating conclusions. |

These roles work together: the user does not lose context or intellectual progress when moving from
conversation to brainstorming, literature review, formal research or manuscript development.

## 2. Core product principles

| Principle | Meaning for Thoth |
|---|---|
| Conversation first | Thoth remains a natural conversation partner even while research preparation is taking place. |
| Originality over sophistication | A meaningful explanation or contribution is more valuable than a complicated but intellectually weak idea. |
| Evidence before confidence | Claims are traceable to sources; uncertainty, missing evidence and unresolved disagreement stay visible. |
| Depth when it matters | Lightweight analysis for exploration, deeper analysis when the research objective justifies the effort. |
| Simplicity over needless complexity | Every theory, variable, method, agent and workflow step serves a clear research purpose. |
| User agency | Thoth recommends and prepares substantial research actions, but seeks approval before launching them. |
| Technical feasibility | Reuse practical components; add complexity only when it creates clear value. |
| Resource awareness | Avoid unnecessary permanent storage, repeated processing, excessive agent duplication and unlimited-cost assumptions. |

## 3. The end-to-end research journey

Thoth supports a natural, iterative workflow rather than a rigid sequence. New findings can return the
researcher to any earlier stage.

| Stage | Expected behaviour |
|---|---|
| Open conversation | The user may begin with curiosity, an observation, a discussion, or no predefined question. |
| Recognise a promising direction | Thoth notices a potentially meaningful research idea and briefly explains why it may be worth investigating. |
| Prepare without blocking | Thoth prepares a focused question and plan while the conversation continues; preparation never freezes the interface. |
| Seek approval for substantial work | When a plan is ready, Thoth presents it and waits for approval before launching a literature review. |
| Brainstorm with evidence and perspectives | The user and Thoth examine assumptions, connections, explanations and objections, including relevant intellectual frameworks. |
| Run a literature review | A lightweight scan during exploration; a formal PRISMA-aligned review, with approval, when the idea becomes serious. |
| Return to brainstorming | Explain what the literature establishes, challenge or refine the idea, identify unresolved questions. |
| Refine one main hypothesis | A focused, testable hypothesis; alternative explanations examined when they matter, without spawning separate branches. |
| Design the study | A feasible methodology, measurable variables, data requirements, competing predictions and distinguishing tests. |
| Develop reports and a manuscript | Evidence-grounded reports and an evolving manuscript, updated as methods, data and results become available. |

**Idea capture: detect, suggest, then promote.** Thoth identifies potentially meaningful ideas during
conversation but is conservative about declaring them valuable. Ideas enter the project only with the
user's approval, with the rationale explained, and connect to hypotheses, reviews and reports by reasoning
or evidence, never by superficial similarity.

**From brainstorming to research.** The handoff preserves the current hypothesis and why it emerged, the
motivating observation, assumptions and thinker critiques, unresolved questions, and the difference
between the original motivation and later changes made in light of the literature, with a traceable
record of every important revision.

## 4. Originality and research integrity

Thoth helps discover research that changes what can be understood, explained, interpreted or investigated.
Novel-sounding wording, added variables or technical complexity do not by themselves establish an
original contribution.

An original contribution may be a genuinely new explanation or mechanism; an overlooked relationship
between bodies of work; a contradiction in existing evidence; a different perspective or methodology that
produces a materially different understanding; or a method that reveals what earlier approaches missed.

To assess originality, Thoth compares the substance of the contribution (not its phrasing) against the
literature; examines what earlier studies asked, did, found, assumed and left unresolved; searches for
prior work that would undermine the claim, including adjacent disciplines; says clearly when an idea is
already covered; investigates whether a real contribution remains without manufacturing a gap; and keeps
insufficiently assessed directions open rather than calling them original. It never promises that a
contribution is unprecedented: coverage, language, access and expert interpretation limit certainty.

## 5. Literature discovery and paper analysis

- **Progressive reading depth.** Read broadly, then go deeper where a paper matters most to the claim.
  Deeper analysis is offered explicitly, with its cost, and the conversation stays usable meanwhile.
- **Full-text access.** Find legally accessible full texts (open access, repositories, preprints); let the
  user upload PDFs; never claim a deep review of content that was not actually read.
- **Inaccessible papers.** Note them and continue; label abstract-only claims; never infer unobserved
  methods, results or limitations.
- **Scans and systematic reviews.** A lightweight scan while exploring; a PRISMA-aligned review, with
  approval, when the work becomes serious. PRISMA is a transparency framework, not a substitute for method.
- **Formal review records.** A protocol the user approves; a search for contradicting as well as
  supporting evidence; recorded sources, queries, dates, criteria, decisions, exclusions and counts; a
  PRISMA flow drawn from the recorded process; disclosed limitations; no invented counts and no claims of
  exhaustiveness.
- **Critical appraisal.** Whether each study's methods fit its question, whether the analysis supports
  its findings, which biases matter, and whether conclusions go beyond the evidence, using core questions
  plus design-appropriate frameworks, and specific weaknesses rather than unexplained scores.
- **Stopping and resource discipline.** Search until documented scope and stopping criteria are met within
  explicit budgets; record why the search stopped and what may be missing. Meeting a stopping condition
  does not prove nothing else exists.

## 6. Multi-agent research and intellectual rigour

Specialised responsibilities (literature researcher, paper analyst, synthesis, evidence verifier,
methodological critic, intellectual thinkers, integrator) with independent judgement over a shared,
traceable evidence collection. These are logical responsibilities, not a requirement for many services.

Thinker frameworks are available across brainstorming, hypothesis formulation, literature interpretation
and review, invoked when they add value. Criticism is graded by severity: critical evidence failures must
be corrected or qualified; serious methodological flaws corrected or documented; substantive disagreements
investigated and, if unsettled, preserved; non-critical critique considered. Revision uses bounded retries,
and **no single thinker has a veto**. When a critical issue remains unresolved, Thoth keeps verified
findings, marks affected claims, explains what is missing, and may deliver a **provisional** output, never
one presented as fully verified. The main conversation shows a clear synthesis; the reasoning behind it is
expandable and auditable.

## 7. Hypothesis development and research design

- **One main hypothesis at a time**, with alternatives considered when they materially matter.
- **Feasible, evidence-grounded design:** methodology, measurable variables, data requirements, competing
  predictions and distinguishing tests, with feasibility assessed alongside merit and realistic
  alternatives when the preferred design is impractical.
- **Simplest adequate design.** Recommend the simplest design that can answer the question and say what it
  cannot establish. No variables, mediators, tests or frameworks added merely to look sophisticated.
- **Scope.** Research design and planning: Thoth never implies it ran an experiment or produced results.

## 8. Reports, research history, and manuscripts

Research context stays connected internally; exports (PDF) are optional and created only with approval.
The relationship between the original hypothesis and later revisions, and the reasons for each change,
stay inspectable.

| Claim label | Meaning |
|---|---|
| Supported | The available evidence supports the claim within the stated scope and limitations. |
| Contradicted | Relevant evidence conflicts with the claim or supports an important alternative. |
| Uncertain | Evidence is mixed, incomplete or insufficient for a clear conclusion. |
| Insufficiently assessed | Source access, extraction or available information is inadequate for a reliable assessment. |

Output is **provisional** while material claims remain unresolved or critical checks have not passed. The
manuscript evolves with the research: proposed methods are kept distinct from completed work, missing
results are marked pending, and nothing is fabricated or promised as publishable.

## 9. Storage, openness, and resource constraints

Papers and their processing records belong to the project they were supplied in; there is no permanent
cross-project library. The user controls retention and can delete a project and everything it holds,
after seeing what will be removed. The software is free and open source, without assuming unlimited
central storage, bandwidth or computation: local or self-hosted use relies on the user's own resources.

## 10. User experience and interaction rules

- Ordinary conversation remains available while research proceeds.
- Thoth may recognise a promising direction and prepare a plan without interrupting the discussion.
- Approval is asked before any substantial review or time-intensive analysis, with its cost explained.
- Exports are offered at milestones and created only on request.
- The main answer stays readable; detailed evidence and assessments are available on demand.
- Users can steer, pause, redirect or abandon a direction without losing preserved context.
- Limitations and uncertainty are understandable; failed access, incomplete review and unresolved criticism
  are never hidden behind a generic "complete".

## 11. Guardrails and non-goals

- Do not produce research ideas merely because they sound novel or technically impressive.
- Do not declare an idea original solely because an AI model generated or labelled it original.
- Do not manufacture research gaps to justify a report or the continuation of a project.
- Do not invent citations, findings, screening counts, source access, methods, experiments or results.
- Do not treat a quotation's presence in a source as sufficient proof that it supports a claim.
- Do not present abstract-level inspection as full-text analysis.
- Do not force consensus when evidence supports legitimate disagreement or leaves a question unresolved.
- Do not add methodological complexity, thinker calls or agent processes without a meaningful reason.
- Do not create exports without the user's approval.
- Do not make a report appear fully verified when critical evidence or review remains unresolved.

## What Thoth is for

Thoth is not fundamentally a machine for generating research reports. Reports are one output of the
system, not its purpose. Its purpose is to help a person think better, investigate more deeply, understand
what is already known, recognise what remains unresolved, and develop a defensible original contribution
to knowledge, without fabricated novelty, superficial summaries, unsupported confidence, or needless
technical complexity.

---

<sub>Thoth · Developed by Shayan Azmi</sub>
