# Thoth — Demo Walkthrough (proof of concept)

A 10-minute script that shows the vision (`THOTH/THOTH.docx`) working in the
running system. Every step lists what to type, what appears, and which vision
section it demonstrates.

## 0. Start it

If an old Thoth server is still running, port 8000 will be busy. Stop it first:

```bash
lsof -ti tcp:8000 | xargs kill
```

```bash
venv/bin/uvicorn backend.main:app --port 8000
```

Open **http://localhost:8000** in a browser. One server serves both the API and the UI.
If the page looks stale, hard-refresh (Cmd+Shift+R).

> Needs internet plus the keys already in `.env` (NVIDIA/Groq/OpenAI for the LLM;
> the paper databases need no key).

---

## 1. Conversation first — no modes (vision §2, §10)

Type in the main box: **`hi thoth`**

- Thoth replies conversationally. No plan, no research launched, no "mode" to pick.
- *Point to make:* there is one input box, and the server decides what kind of turn it is.

## 2. Recognise a promising direction + prepare without blocking (vision §3, §3.1)

Type: **`Why do night-shift nurses report more burnout despite similar workloads?`**

Within a few seconds you see:

1. **"Idea worth capturing?"** card: Thoth noticed a *contradiction* (one of the
   five originality triggers in vision §4.1). It has **not** been saved. You can
   click **Promote to idea network** (saves it with your approval) or **Not now**.
2. **"I've sketched a plan"** card: the research question, objectives, and:
   - **Mode: Lightweight literature scan (v1)**
   - **Estimated effort:** up to 20 papers (abstracts only), no full texts, ~4–8 LLM calls, 1–4 min.
- *Point to make:* nothing expensive has started. The chat box stays usable.

## 3. Seek approval (vision §2 "User agency", §10)

Click **Approve this plan** (or type `approve`).

- `✓ Approved (v1)` → task launched. Only the exact version you approved can run.

## 4. Lightweight scan, not a formal review (vision §5.4)

About 15 seconds later:

- **Lightweight scan: N papers (cap 20)**: each paper is labelled `abstract_only`.
  The note states plainly that no full texts were read and that there are no screening counts.
- **"I'd recommend a formal review"** appears *only if* maturity signals exist
  (e.g. disconfirming papers surfaced). It lists the reasons and the extra effort,
  and **does not start anything**.

## 5. The report, then critical passes on it (vision §6.3, §4, §8)

Progress lines appear ("Drafting the synthesis…", "Checking each claim… (Truth Guard)").
**Expect 3–4 minutes** here: the writer and verifier make several LLM calls, and if the
primary model is slow, Thoth falls back to Groq. Fill the time by explaining steps 1–4,
or show that the chat still answers a side question while the run continues.

- The **final synthesis report**. In a scan, its *Methodology* section is written by
  Thoth from what actually happened (one search, abstracts only, no screening), never
  invented by the LLM (vision §11).
- **Thinker perspective** (e.g. *David Hume*, because the question is causal) with
  *why this thinker* and a challenge. The severity gate is **advisory, no veto** (vision §6.4).
- **Originality:** one of `likely_novel | partial_overlap | substantially_covered | insufficiently_assessed`,
  with the **adjacent-field searches it actually ran**, the closest prior work, and its limits.
  *Point to make:* it can never say `likely_novel` without adjacent searches (guardrail, vision §4.2).
- **Report status: 🟡 PROVISIONAL** with the open gaps listed (e.g. "Lightweight scan only",
  unresolved citations). A report is only `fully_reviewed` when every check passes (vision §8.3, §11).
  *"Offered only on request — no PDF has been created."* (vision §8.1)
- **Where we could go next:** follow-up questions (return to brainstorming, vision §3 stage 7).

## 6. Escalate to a formal PRISMA review, with its own approval (vision §5.4, §5.5)

Type: **`this is serious now, run a formal review`**

- A **new plan card, v2**, **Mode: Formal PRISMA-aligned review**, with the larger effort
  estimate (~60 papers, up to 15 full texts, 5–15 min).
- The earlier v1 approval **cannot** launch it. Click **Approve this plan** again.
- The run now includes citation snowballing, full-text retrieval and a
  **"Formal PRISMA review recorded"** card with identified / screened / included counts
  taken from the actual recorded ledger.

*(Allow 5–15 minutes. For a short demo, show steps 1–5 live and describe step 6,
or start step 6 at the beginning of the meeting.)*

---

## Tips

- Type side questions in the chat while a run is going. Avoid phrasing like
  "run/do/start a formal review" unless you want to escalate. Just mentioning PRISMA is fine.
- The Approve and Promote buttons disable after one click.
- Wiki-style source tags like `[[src-…]]` in the report are vault note links, not broken citations.

## What to say is NOT done yet (honest scope)

| Vision | Status in this proof of concept |
|---|---|
| §7.2 Feasibility probe for study design | Not built |
| §9 Project-scoped paper storage + retention controls | Not built |
| §6.3 Thinkers at *every* stage (brainstorm, hypothesis) | Wired at critical review only |
| §8.2 Claim labels | Shown when the Truth Guard audits individual claims; otherwise reported as a gap |
| §10 Cost estimates | Rough effort ranges, not metered cost |
| §12 Deployment model | Undecided |

## Automated check

```bash
venv/bin/pytest backend/tests/scenarios/ -q
```

S1 (conversation never blocks), S2 (idea capture), S3 (scan vs formal, originality guardrail,
provisional status).
