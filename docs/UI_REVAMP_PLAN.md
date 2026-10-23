# Thoth UI Revamp Plan (v3: journey, brand, borrowed patterns)

*Rewritten 24 Oct 2026 after a second interview with the project owner. Governed by `THOTH/THOTH.docx`; if this plan contradicts the vision, the vision wins. This plan covers the UI only. The research workflow logic behind each stage will be reworked separately.*

## 1. The idea in one paragraph

People arrive with something vague: an observation, a hunch, a question they can't phrase yet. They **talk** with Thoth, which mostly asks sharpening questions. Along the way they **think with philosophers** (one thinker joins the chat, a council of all ten weighs in, two debate, or a one-on-one room). One **hypothesis** takes shape and visibly evolves. They **check** it against the literature, run a **formal PRISMA review** when the idea is serious, and end with a **research draft**. The UI makes this path visible and natural. Every stage is also reachable directly ("just make me a PRISMA review", "let me talk to Popper") without forcing anyone through the whole path.

### Two ways in, one place

- **Guided:** keep talking; Thoth notices when a stage becomes possible and offers it.
- **Direct:** a door on the home screen, a slash command, or a click on a journey stage starts that stage immediately.

These are **actions, not modes**. Starting `/review` opens a review plan (which still waits for approval); afterwards you are back in the same conversation. There is no toggle that changes how the chat behaves, so the vision's "conversation first, no mode lanes" rule holds.

## 2. Decisions from the interviews

| Topic | Decision |
|---|---|
| Audience | Real researchers; demo path polished first |
| Brand | "The honest scribe": built on Thoth recording the verdict at the weighing of the heart, the scribe's two inks, and the moon as reckoner of time (no gold/pyramid styling) |
| Feel | Scholarly and calm; 3D only where it earns its place (intro, thinker busts). **No gimmicky visuals.** |
| Theme | Light and dark designed equally, follows the system setting |
| Tech | Vanilla JS, split into modules |
| Devices | Fully responsive |
| Journey visibility | A path showing the stages; reachable by talking *or* by picking a stage directly |
| Home | Big open question + a row of doors (Brainstorm · Talk to a thinker · Check a hypothesis · Literature review · Draft) |
| Shortcuts in chat | Slash commands with autocomplete |
| Thinkers | All four forms: join the chat, council (all thinkers), debate (two thinkers), one-on-one room |
| Debate picks | Thoth or the user picks the two most relevant; any thinker can also be opened individually |
| Thinker look | Subtle 3D busts |
| Thoth's voice | Socratic first, then knowledgeable colleague, then warm companion |
| Hypothesis | Pinned living card + its own page + central node on the research map |
| Check result | Verdict first → what's answered and what's open → evidence for vs against |
| PRISMA | Live flow diagram on top, decisions table below |
| Draft | Full-screen editor with an evidence drawer (my call; see 4.8) |
| Workspace | Changes with the stage by default; user can open any panel manually and pin it |
| Nudges | Suggestion chips + glowing next stage + explicit card (weighted, see 6) |
| Map | A Research Map view showing how the work grew |
| Projects | Collapsible left sidebar of projects |
| Intro | 3D cinematic, first visit only, skippable |
| Transparency | Live activity timeline |
| Editing | User edits directly (claim re-checked) and Thoth proposes tracked changes; all versioned |
| Borrowed patterns | Claude: side panel with versions, inline step summaries, citation chips, projects with a brief, attachments, message branching. SciSpace: column tables with custom columns, highlight-to-ask reader, tagged notes, `/cite` from Library, export. See §12 |
| Inspirations | Claude/ChatGPT (conversation, projects), Notion/Google Docs (editing), Elicit/Perplexity/SciSpace (sources, paper tables, reading papers), Obsidian (linked notes, graph) |

## 3. Brand: the honest scribe

Researched 24 Oct 2026 (sources at the end of this section). The brand takes from Thoth only what matches the product, and leaves out the rest.

### 3.1 What the myth gives us

| What Thoth was | What it means for the product | Where it shows in the UI |
|---|---|---|
| **The scribe at the weighing of the heart.** He "stands before the scales… and records the verdict"; he does not set it. | Thoth reports what the evidence shows and never decides the answer it wants. This is the core promise ("evidence before confidence"). | Claim labels, report status and the Check verdict are presented as *the record*: plain, sourced, never inflated. |
| **Inventor of writing; patron of scribes.** | Writing is the product's material. The draft is the destination, not an export. | Type is the hero of the visual identity; the draft editor is a first-class screen. |
| **The scribe's palette had two inkwells: black for the text, red for titles and corrections.** | A colour system with history behind it: black ink is the user's content; red ink is Thoth's corrections and headings. | Tracked changes and suggested fixes appear in red-ochre ink; section headings (rubrics) use it sparingly. Everything else is ink on paper. |
| **Moon god and "reckoner of times and seasons"** (lunar disc on a crescent). | Progress through the research is measured, not rushed. | The **journey path is drawn as moon phases**: Explore is a new moon, Draft a full moon. Each stage fills more of the disc. |
| **His name means "he who is like the ibis"; Egyptians read the ibis beak's curve as the crescent moon.** | The mark can join both symbols in one line. | **Mark:** a lunar disc whose crescent is the ibis's beak in profile. |
| **Mediator and counsellor in disputes between gods;** in the Horus–Set contest he recorded events, advised, and healed both sides to keep the contest fair. | Thinker debates need a fair moderator with no side to take. | In debates and councils Thoth moderates, records each position fairly, and summarises; no thinker wins by veto (vision §6.4). |
| **Paired with Seshat, "Mistress of the House of Books",** keeper of the House of Life (library, scriptorium and school in one). | A research project is a library, a writing room and a place of learning together. | The project space brings together papers, notes and drafts. (Named plainly in the UI, e.g. "Library"; the House of Life stays in the brand story.) |
| **"Thrice great" (Hermes Trismegistus).** | The vision's three roles: companion, investigator, research-development partner. | Brand story line: *one companion, three roles*. |
| **Plato's *Phaedrus*:** Thoth offers writing to King Thamus, who warns that it gives "the appearance of wisdom" instead of the real thing. | Thoth (the product) answers that warning: never produce the look of knowledge without the substance. This is "originality over sophistication" and "no fabrication". | Brand manifesto and About page. It guides copy: no confident-sounding filler. |

### 3.2 Identity

- **Mark:** lunar disc resting on a crescent; the crescent's inner curve is the ibis's beak. One continuous ink line, readable at 16px, no face. The god is never drawn as a character; the thinkers have busts, Thoth has a sign.
- **Tagline options:** *"Find the questions worth asking."* · *"Record what the evidence shows."*
- **Palette (all as tokens, light and dark):**

| Token | Light | Dark | Source of the idea |
|---|---|---|---|
| `--paper` | pale papyrus with a faint green-grey tint (not cream) | night indigo | papyrus by day, the moon god's night |
| `--ink` | carbon black-brown | moonlit off-white | the black inkwell |
| `--rubric` | red ochre (earthy, not neon) | warmer, lighter ochre | the red inkwell: corrections, headings |
| `--moon` | soft silver | pale silver | lunar disc: journey phases, the mark, focus states |
| claim colours | supported green · contradicted red · uncertain amber · insufficiently assessed grey (with patterns) | same, tuned for dark | semantic only; kept separate from `--rubric` so a correction never looks like a verdict |

- **Type:** the brand is typographic. Headings in a book serif with visible stroke contrast, the closest digital echo of a reed pen. A humanist sans for UI and conversation, and a mono for queries, counts and IDs.
- **Motion vocabulary (calm, few):**
  - *Ink stroke:* progress is a reed line being drawn, not a spinner.
  - *Moon fill:* a journey stage completes by its disc filling.
  - *Ink settling:* new content fades in like ink drying, under 200 ms.
  - The thinker busts turn slightly when speaking. Nothing else moves without a reason.
- **Voice:** the counsellor. Asks the sharpening question, gives each side a fair hearing, says plainly what is known and what isn't. No "divine", "ancient" or "oracle" copy.

### 3.3 What we deliberately leave out
Gold and bronze, pyramids, hieroglyph wallpaper or borders, the Eye of Horus (overused, with occult associations), papyrus-scroll textures, faux-Egyptian fonts, and the baboon form. The mythic layer lives in the mark, the moon-phase journey, the two inks and the intro, and nowhere else.

### 3.4 Sources
[Wikipedia: Thoth](https://en.wikipedia.org/wiki/Thoth) · [World History Encyclopedia: Thoth](https://www.worldhistory.org/Thoth/) · [Egyptian Museum: Thoth](https://egyptianmuseum.org/deities-thoth) · [University of Memphis: Scribal Palette](https://memphis.edu/egypt/exhibit/palette.php) · [Musée des Beaux-Arts de Lyon: Scribe's palette](https://www.mba-lyon.fr/en/fiche-oeuvre/scribes-palette) · [World History Encyclopedia: Seshat](https://www.worldhistory.org/Seshat/) · [Wikipedia: Eye of Horus](https://en.wikipedia.org/wiki/Eye_of_Horus) · Plato, *Phaedrus* 274c–275b.

## 4. Screens

### 4.1 Cinematic intro (first visit, ~6 s, skippable)
Night; a crescent rises and is revealed as an ibis's beak in profile → a reed stroke in black ink writes *"Which questions are worth asking?"*, with one word corrected in red ochre (the scribe's two inks) → points of light (papers) join the crescent into the full lunar mark → the mark settles into the logo. Three.js; plays once; reduced-motion and no-WebGL fallbacks; never on later visits beyond a slow ambient moon behind the home screen.

### 4.2 Home
```
                ☽  THOTH
        What's been on your mind?
   ┌────────────────────────────────────┐
   │ I noticed something odd about...   │
   └────────────────────────────────────┘
 [Brainstorm] [Talk to a thinker] [Check a hypothesis]
 [Literature review] [Draft]
   Recent projects: Night-shift burnout · Urban heat…
```
Typing starts a guided conversation. A door starts that stage directly (e.g. *Talk to a thinker* opens the thinker picker; *Literature review* asks for the topic, then shows the review plan).

### 4.3 Conversation workspace
```
┌────────┬─ ● Explore ─ ● Thinkers ─ ◉ Hypothesis ─ ○ Check ─ ○ Review ─ ○ Draft ─┐
│Projects│ ┌ HYPOTHESIS v3 ─────────────────────────┐ │ Workspace (stage-aware)  │
│        │ │ Night-shift burnout is driven by…      │ │ [Ideas][Thinkers][Evid.] │
│        │ └ history · open · check → ──────────────┘ │ [Review][Draft]   📌     │
│        │  Thoth: What would you expect to see if…  │                          │
│        │  [Turn into hypothesis] [Ask Popper]      │                          │
│        │                                           ├──────────────────────────┤
│        │  [ / message…                     ]       │ Activity timeline        │
└────────┴───────────────────────────────────────────┴──────────────────────────┘
```
- **Journey path** along the top, drawn as **moon phases** (new moon = Explore … full moon = Draft): completed stages are filled discs, the current one is ringed, future ones are faint outlines. Every stage is clickable. A stage glows softly in moon silver when it becomes possible.
- **Hypothesis card** pinned under the path once one exists (see 4.5).
- **Conversation:** short replies with expandable detail; cards stay compact and open their detail in the workspace.
- **Workspace** follows the current stage, but any panel can be opened from its tabs and **pinned** so it stays when the stage changes.
- **Activity timeline:** every system step as a row (time, what happened, expandable to queries, sources, model used, retries).

| Stage | Workspace shows by default |
|---|---|
| Explore | Ideas noticed so far (suggested and promoted), open questions |
| Thinkers | Objections raised, by thinker; questions still unanswered |
| Hypothesis | Hypothesis page: statement, origin, assumptions, falsification criteria, versions |
| Check | Verdict, answered vs open questions, evidence for vs against, originality |
| Review | PRISMA protocol, live flow diagram, decisions table |
| Draft | Outline and claim status overview (the editor itself is full screen) |

### 4.4 Thinkers: four forms, one roster

| Form | What happens | How to start |
|---|---|---|
| **Joins the chat** | A thinker enters the conversation with their bust and voice; Thoth moderates and can step back in | Thoth's chip "Ask Hume?", or `/hume` |
| **Council** | All thinkers give a one-line take on the current idea in a panel; pick anyone to go deeper | `/council`, or the Thinkers tab |
| **Debate** | Two thinkers argue about the idea; the user can interject any time. Thoth suggests the two most relevant (with reasons); the user can swap either | `/debate`, or `/debate popper kuhn` |
| **One-on-one room** | A focused full-width conversation with one thinker in their own style; on leaving, a summary of what changed returns to the main conversation | the thinker's bust → "Talk alone", or `/room popper` |

- **Busts:** small stylised 3D busts, monochrome in the ink palette, that turn slightly when speaking. Static images on phones and with reduced motion.
- Every thinker message is marked as that thinker's perspective. No thinker gets a veto; disagreement is shown, not resolved by force (vision §6.4).

### 4.5 The hypothesis: card, page, node
- **Pinned card:** current statement, version, and a one-line trail ("refined after Popper (v2), Hume (v3)"). Actions: history, open, edit, check.
- **Hypothesis page:** statement; where it came from (the original observation, kept unchanged); assumptions and definitions; objections from thinkers; falsification criteria; version history with what changed and why (vision §3.2).
- **Map node:** the centre of the Research Map.
- One main hypothesis at a time (vision §7.1). Alternatives appear as notes on the page, not as parallel branches.

### 4.6 Check
1. **Verdict** headline, e.g. *"Partly supported · partly covered by prior work."*
2. **What the evidence answers / leaves open:** short question list that suggests the next step (refine, formal review, or drop).
3. **Evidence for vs against** in two columns, each paper with its reading-depth badge (abstract only / full text).
4. **Originality** verdict with the adjacent-field searches it ran and the closest prior work.
- Never shows a verdict stronger than the evidence; abstract-only evidence is labelled as such.

### 4.7 Literature review (PRISMA)
- Starts with the **protocol** (question, scope, databases, inclusion/exclusion criteria, effort estimate) to adjust and **approve**.
- While running: the **PRISMA flow diagram builds live**: boxes fill with real counts as decisions are recorded. Click any box to see those papers and reasons.
- Below it: the **decisions table** (paper, stage, include/exclude, reason, access level), filterable. Paper rows open a reading view in the style of SciSpace/Elicit: abstract, extracted methods/findings where full text was available, and which claims cite it.

### 4.8 Draft: full-screen editor with an evidence drawer
- A calm full-screen document (in the style of Google Docs/Notion) with sections appropriate to the paper type and stage; pending sections are marked as pending, never filled with invented results.
- Each claim carries a small label chip. Clicking a paragraph or chip slides in the **evidence drawer** from the right: the source passages, the claim's label and reason, and Thoth's suggested fix.
- **Edits:** the user types freely; an edited claim is re-checked and its label updates. Thoth's suggestions appear as tracked changes to accept or reject. Every accepted change makes a version; history shows diffs and reasons.
- Report status (Provisional / Fully reviewed + open gaps) stays visible at the top. PDF export only on request.

### 4.9 Research Map
A full view (in the style of Obsidian's graph, but structured by the journey): curiosity → thinker conversations → hypothesis versions → evidence → review → draft, as connected nodes. Click a node to open it. It grows as the project grows, so it shows how the idea developed. Not animated except when a node is added.

### 4.10 Projects sidebar
Collapsible. Each project shows its current stage. Inside: conversations, the hypothesis, reviews and drafts. Everything (papers, notes) belongs to its project (vision §9).

## 5. Slash commands
Autocomplete appears on `/`.

| Command | Action |
|---|---|
| `/brainstorm` | Open exploration prompt |
| `/council` | All thinkers weigh in |
| `/debate [a] [b]` | Two thinkers debate (Thoth picks if none given) |
| `/popper`, `/hume`, … | That thinker joins the chat |
| `/room [thinker]` | One-on-one room |
| `/hypothesis` | Draft or open the hypothesis |
| `/check` | Check the hypothesis against the literature (lightweight scan) |
| `/review` | Formal PRISMA review: protocol first, needs approval |
| `/draft` | Open the draft editor |
| `/map` | Open the Research Map |

## 6. Nudges: how Thoth moves things forward without nagging

| Weight | Form | Used for |
|---|---|---|
| Light | **Suggestion chips** under a reply | "Turn this into a hypothesis", "Ask Popper", "Check the evidence" |
| Medium | **Stage glows** on the path | A new stage has become possible |
| Heavy | **Explicit card** with reasons + Yes / Not yet | Anything substantial or costly: formal review, deep paper analysis, PDF export (always needs approval, vision §10) |

At most one heavy card at a time; dismissed nudges don't repeat for the same idea.

## 7. Thoth's voice
Mostly **Socratic** (asks the question that sharpens the idea), then a **knowledgeable colleague** (says what the literature or theory suggests, plainly), then a **warm companion** (encouraging, never pushing research early). Short replies by default; detail behind "more".

## 8. Responsive
- **Desktop:** sidebar · conversation · workspace, journey path on top.
- **Tablet:** sidebar becomes icons; workspace is a slide-over.
- **Phone:** single column; the journey path becomes a compact stage pill ("Hypothesis · 3 of 6"); bottom bar: Chat · Hypothesis · Workspace · Map. Busts and intro become static or 2D.

## 9. Backend support the UI will need (for the later workflow work)
Thinker conversations as first-class turns (join / council / debate / room) · hypothesis versions with reasons · stage state per project · per-claim re-check and suggestion endpoints · report versions · structured report (sections + claims with IDs) · an `activity` event per pipeline step · live PRISMA counts as events · projects linked to sessions and briefs. SQLite schema and Postgres migrations move together.

## 10. Build order (UI)
1. **Shell & identity:** tokens (two inks, moon silver), mark, light/dark, home with doors, conversation workspace, moon-phase journey path, projects sidebar (recents, starred, project brief), PDF attachments, responsive layout, side-panel version arrows.
2. **Slash commands, nudges, inline step summaries:** autocomplete, chips, stage glow, explicit cards, collapsible step line in replies.
3. **Hypothesis card & page** and **Check** view, with claim chips that show reading depth.
4. **Thinkers:** join-the-chat and council first, then debate (Thoth as fair moderator) and one-on-one room; busts.
5. **PRISMA view & Library:** protocol approval, live flow diagram, column-model tables with custom columns and export, paper reader with highlight actions (explain · support/challenge · note · ask a thinker), tagged notes.
6. **Draft editor:** evidence drawer, red-ink tracked changes, version arrows, `/cite` from Library.
7. **Research Map, activity timeline, message branching.**
8. **Cinematic intro.**

Steps 1–3 give a demo-able journey; each step ends with a walkthrough from the user's seat.

## 11. Open questions
- Should a one-on-one room's summary need the user's OK before it is added to the hypothesis page?
- Should debates have a turn limit (e.g. 3 exchanges each) before Thoth summarises?
- Thinker roster: keep the current 10, or add others later (e.g. Feyerabend, Peirce)?

## 12. Patterns borrowed from SciSpace and Claude

Researched 24 Oct 2026. Each pattern is adapted so it keeps Thoth's guardrails: honest reading depth, no mode toggles, approval before costly work, no invented citations.

### 12.1 From Claude

| Claude pattern | In Thoth | Adapted how / guardrail |
|---|---|---|
| **Side panel next to the chat** (Artifacts) that updates while you keep talking, with a version switcher (◀ v2 ▶) | The stage-aware workspace; hypothesis and draft each get ◀ v3 ▶ version arrows | Every version also stores *why* it changed (vision §3.2, §8.1) |
| **Collapsible "thinking / steps" block** inside a reply | Each long-running reply carries a one-line step summary ("Searched 5 databases · 17 papers · 3 claims contradicted") that expands into the steps | Same data as the activity timeline, shown in place; model fallbacks and retries visible when expanded |
| **Inline citation chips** that reveal the source on hover/click | Claim chips in replies and the draft, showing label + source passage | Chip shows reading depth (abstract only / full text); never shows a passage that wasn't actually read |
| **Projects with their own files and instructions** | A project holds its Library (papers, uploaded PDFs), notes, hypothesis, reviews, drafts, and a short **project brief** (field, constraints, available data/resources) | The brief later feeds the feasibility probe (vision §7.2); papers stay in their project (vision §9) |
| **Attach files in the message box** (chips above the input) | Drop or attach PDFs; they appear as chips and land in the project Library | Upload is the vision's route for inaccessible papers (§5.2); a paper is marked full text only after extraction succeeds |
| **Edit an earlier message, branches with ◀ 1/2 ▶** | Edit and resend a message to explore another phrasing; branch arrows on that message | Conversation branches only. There is still **one** pinned hypothesis (vision §7.1); promoting from a branch replaces or revises it explicitly |
| **Research keeps running while you chat**, with an indicator | Already the rule; a small moon-phase indicator on the stage shows work in progress | Unchanged |
| **Recents and starred chats in the sidebar** | Projects sidebar with recent and starred conversations inside each project | — |
| **"+" menu that switches Research on (blue indicator)** | **Not adopted as a toggle.** Thoth uses slash commands, home doors and stage clicks that *start an action* | A persistent "research on" switch is a mode lane, which the vision rules out |

### 12.2 From SciSpace

| SciSpace pattern | In Thoth | Adapted how / guardrail |
|---|---|---|
| **Literature table with columns** (TL;DR, methods, conclusions, limitations) and **custom columns** created by asking a question | Papers tab and PRISMA decisions table use the same column model; the user can add a column like "Sample size?" or "Measures circadian disruption?" | Each cell shows where its value came from (abstract / full text) or says "not reported in what was read"; nothing is filled in by guesswork |
| **Reader with highlight-to-explain** (select a passage, ask the copilot) | Paper reading view: select text → *Explain* · *Does this support or challenge my hypothesis?* · *Save as note* · ***Ask a thinker about this*** (e.g. send the passage to Popper) | The thinker option is unique to Thoth and links reading back to the brainstorming |
| **Colour-coded saved notes** from passages | Notes tagged *supports* / *challenges* / *question*, linked to the claim or hypothesis they bear on | Tags use the claim colours; the Research Map shows these links |
| **Step-by-step agent progress** (search → filter → extract → synthesise) | The activity timeline and the live PRISMA flow diagram | Counts come only from recorded decisions (vision §5.5) |
| **AI Writer that inserts citations** from your library | Draft editor `/cite` inserts only from the project Library, with the claim chip attached | No citation can be inserted that isn't a real, stored source |
| **Export table as CSV / BibTeX** | Export button on the Papers and decisions tables | User-initiated download; PDF of reports still needs explicit approval (vision §8.1) |
| **Several review depth options** | Two depths only: lightweight scan (`/check`) and formal PRISMA (`/review`) | Matches the vision's scan-then-formal model; a middle tier would blur what "formal" means |

### 12.3 Where these land in the build order (folded into §10)
- **Step 1 (shell):** side-panel versions, projects with brief, attachments, recents/starred.
- **Step 2:** inline step summaries in replies.
- **Step 3 (Check view):** claim chips with reading depth.
- **Step 5 (PRISMA view):** column-model tables, custom columns, export, paper reader with highlight actions and notes.
- **Step 6 (Draft):** `/cite` from Library, version arrows.
- Message branching: after step 6, once hypothesis versioning exists.

### 12.4 Sources
[SciSpace review (Educators Technology)](https://www.educatorstechnology.com/2026/09/scispace-review.html) · [SciSpace vs ChatPDF (SciSpace)](https://scispace.com/compare/chatpdf) · [SciSpace guide (CASRAI)](https://www.casrai.org/guides/scispace) · [SciSpace review (Unite.AI)](https://www.unite.ai/scispace-review/) · [What is SciSpace? (HSLU)](https://blog.hslu.ch/information-literacy-toolkit/scispace/) · [Intro to Artifacts (Anthropic)](https://support.claude.com/en/articles/9945615-intro-to-artifacts) · [Use Research on Claude (Anthropic)](https://support.claude.com/en/articles/11088861-use-research-on-claude.md) · [Claude for research (CASRAI)](https://casrai.org/guides/claude-for-research-capabilities-and-compliance-limits)
