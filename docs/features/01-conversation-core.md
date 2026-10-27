# 01 · Conversation core (the conductor)

> Vision: §2 conversation first, §3 stages 1-4 and 7. **Built 24 Oct 2026**: see
> [`docs/archive/verify/conversation_core.md`](../archive/verify/conversation_core.md) for the walkthrough and known gaps.

## What the owner wants

- It feels like a normal chat to someone who has never seen Thoth.
- Thoth remembers the whole project: thread (summarised when long), hypothesis, papers, thinker notes.
- The first reply to a curious question is a brief answer, marked as unchecked, plus one sharp question.
- Facts from the model's own knowledge are allowed, but labelled *general knowledge, not yet checked*,
  with a one-tap **Check this**.
- Thoth suggests the next step; the user decides. Research is offered only once the idea is specific
  enough, and no more than once until the user answers.
- Reply length is adaptive.
- The Autopilot / Co-pilot switch lives at project level (see 02), with per-step override.

## What's wrong today

`_classify_turn` routes every message down one of six fixed paths before anything understands it.
The casual path sends only the latest message to the model (`direct_chat_prompt` has `{user_query}`
and nothing else). Every other substantive message falls through to `RESEARCH_INTENT` and makes a
new brief. So Thoth both forgets and over-reacts.

## Design

One **conductor** agent (Thoth) handles every turn. It reads the project context, replies, and may
call tools. Tools are split by cost:

| Tool | Cost | Runs | What it does |
|---|---|---|---|
| `quick_look(query)` | seconds | freely, at most once per turn | ~5 papers via Librarian (title, year, venue, abstract, link); returns a short cited answer. Tier ① in 05 |
| `propose_notebook_update(section, value)` | free | freely | Emits a proposal card ("Set question to: …"). Never writes directly |
| `suggest_thinker(thinker_id, why)` | free | at most once per few turns | "Hume would have something to say about this causal leap. Bring him in?" |
| `offer_step(step, estimate)` | free | when readiness is met | Offers scan / trial / systematic review / design / draft with a time + scope estimate. Starts nothing |
| `recall(query)` | cheap | freely | Search project memory (past turns, paper records, thinker notes) |

Heavy steps (scan, systematic review, trial, full council review, design, draft) are **never** started
by the conductor. They start only from an explicit user action, or once under Autopilot after a single
up-front approval. That keeps the `is_approved()` gate from `conversation/brief.py`.

### Turn flow

```
user message
  → load context: rolling summary + last ~12 turns + notebook snapshot + open proposals
  → conductor (strong model, tool calling)
       ├─ reply text (streamed)
       ├─ 0..n tool calls (quick_look / propose / suggest / offer / recall)
       └─ "unchecked" spans: claims made from general knowledge
  → SSE to the client: token stream, tool cards, claim labels
  → persist the turn; refresh the summary every ~10 turns
```

Structured approvals (`approval`, `idea_promotion`, and the new `notebook_accept`) skip the conductor
and go straight to their handlers. That's the only part of `_classify_turn` that survives.

### Readiness (when to offer research)

The conductor offers a scan only when **all** of these hold, and then not again until the user responds:
1. there is a statable question or claim (it can propose one for the notebook);
2. it names at least one concrete construct (e.g. "burnout", "night shift");
3. the user isn't mid-exploration. If their last two messages were open musing, keep talking.

This replaces the heuristic idea detector's "fire on any trigger word" behaviour.

### Labelling unchecked claims

The conductor marks claims made from its own knowledge with a span tag (`<unchecked>…</unchecked>`).
The UI renders each one with a dotted underline and a **Check this** link, which runs `quick_look` on it.
A `quick_look` result replaces the label with citations, or with "couldn't confirm".

## Data

- `turns(project_or_thread_id, role, content, tool_calls_json, created_at)`: server-side, replacing
  the localStorage-only history.
- `thread_summary(thread_id, summary, through_turn_id)`
- `proposals(id, thread_id, kind, payload_json, status: open|accepted|edited|dismissed)`

Per `CLAUDE.md`, the SQLite tables in `memory/db.py` and a new Postgres migration ship together.

## Events (SSE)

`turn_start`, `token`, `unchecked_claim`, `quick_look_result`, `notebook_proposal`,
`thinker_suggestion`, `step_offer` (with `estimate`), `turn_end`, `error`.
The old `plan_pending` is folded into `step_offer`.

## Agent and prompt

The conductor prompt is in [09 § Thoth](09-agents-and-prompts.md#thoth-conductor).
Model: `nvidia/nemotron-3-ultra-550b-a55b` (5s on the 24 Oct probe), falling back to `openai/gpt-oss-20b`.

## Walkthrough (acceptance)

1. New thread: "why do night-shift nurses burn out more?" → a 2-4 sentence answer with at least one
   unchecked label, plus one question. No plan card.
2. Reply "mostly sleep, I think". Thoth's answer refers back to night shifts, which proves memory.
3. After the idea names constructs, one `notebook_proposal` appears ("Question: …"). Accept it, and it shows in the notebook.
4. Tap **Check this** on a label → citations replace it, or "couldn't confirm".
5. Thoth offers a scan once, with an estimate. Ignore it and keep chatting: it isn't offered again
   until you respond.
6. Nothing heavy has started at any point (task table empty).

Scenario test: `backend/tests/scenarios/test_s10_conductor_memory_and_offers.py`.

## Open questions

- ~~Does Ultra on NIM support OpenAI-style tool calling?~~ Yes (probed 24 Oct).
- As built, the reply is sent whole as `direct_answer` (with `unchecked` and `tools` fields) rather than
  token-streamed; `plan_pending` still exists and now follows an accepted offer (`step_accept`).
