# 📝 Shayan's Notes — Feynman Architecture Study

> These are my takeaways, preferences, and open questions from studying Feynman's architecture.
> Goal: **Find and develop a better architecture for simple systems — not overly detailed, but great.**

---

## ✅ What I Liked & Want to Keep

### 1. How It Handles API Calls & Speed
- The parallel fan-out pattern (Researcher + Reviewer running at the same time)
- Smaller payloads per agent = faster responses = cheaper
- **I want this approach** but adapted for a simpler system

### 2. "Deliberately Just the Agent Turn" (Pi Runtime philosophy)
- Plan → Act → Observe → Replan — that's it, no overengineered framework
- **Good principle** — keep my system lean

### 3. Integrity-First Research
- "Never fabricate a source", "URL or it didn't happen", "Read before you summarize"
- **I want this in my system** — add these integrity rules to my Writer and Critic prompts

---

## 🔧 Features I Want — With Config Options

### Scoped Context (Smaller Payloads per Agent)
- **Default**: ON — each agent gets only what it needs, not the full blob
- **Advanced Config**: Let user toggle to send full context if they want deeper cross-referencing
- The tradeoff: smaller context = faster + cheaper, full context = potentially more coherent but slower

### Configurable Thinking Levels
- **Default**: Best optimal setting based on task type (e.g., high for research, medium for verification)
- **Advanced Config**: Let user manually adjust thinking level
- **Must tell user**: "Increasing or decreasing this affects answer quality"
- **Show a recommended range** with quality/error tradeoffs

#### 🔬 Open Question: How to find optimal thinking levels without trial-and-error?
Ideas to research:
- Look into **model calibration metrics** — some models expose confidence scores
- **Automated eval pipelines** — run same prompt at different thinking levels, score outputs against a rubric automatically (LLM-as-judge, which I already have with the Critic chain)
- Check if NVIDIA's NIM API exposes any **quality/latency metadata** per response
- Could build a small benchmark: 5-10 known-answer questions, test each thinking level, log quality + latency + cost → build a lookup table
- Research: "reasoning token budget vs output quality" papers

### File-Based State Persistence
- **Optional** — not core to my system right now
- Maybe add later for crash recovery / resumability

---

## 🤔 Things I Need Explained Better

### Runtime Patching & Shim Management — ELI5

**What is it?**
When Feynman starts up, it does this:
```typescript
patchPiRuntimeNodeModules(options.appRoot, options.feynmanAgentDir);
```

Think of it like this:

```
┌──────────────────────────────────────────────────────┐
│                  Your App Starts                      │
│                                                       │
│  Normal way:                                          │
│  ┌─────────┐     ┌──────────────┐     ┌─────────┐   │
│  │ Your Code│────▶│ Library v2.1 │────▶│ LLM API │   │
│  └─────────┘     └──────────────┘     └─────────┘   │
│                                                       │
│  With Runtime Patching:                               │
│  ┌─────────┐     ┌──────────────┐     ┌─────────┐   │
│  │ Your Code│────▶│ Library v2.1 │────▶│ LLM API │   │
│  └─────────┘     └──────┬───────┘     └─────────┘   │
│                          │                            │
│                   ┌──────▼───────┐                    │
│                   │  SHIM/PATCH  │ ◄── intercepts     │
│                   │ • add retry  │     the library     │
│                   │ • add limits │     BEFORE it       │
│                   │ • fix bugs   │     talks to API    │
│                   └──────────────┘                    │
└──────────────────────────────────────────────────────┘
```

**In plain words:**
- A **shim** is a thin layer of code that intercepts calls between your code and a library
- **Runtime patching** = modifying how a library works *after* it's installed, without changing its source code
- Feynman uses this to:
  - **Inject rate-limit interceptors** into the API client — so every LLM call automatically gets retry/backoff logic
  - **Fix compatibility bugs** in dependencies without waiting for an upstream fix
  - **Add custom logging/telemetry** without modifying library code

**Python equivalent** (what you could do):
```python
# Instead of patching at runtime, in Python you'd typically use:
# 1. Middleware/decorators
# 2. Monkey-patching
# 3. Wrapper classes

# Example: wrapping your LLM with retry logic
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def safe_llm_call(chain, inputs):
    return chain.invoke(inputs)
```

**Do I need this?** Probably not at this stage. It's a TypeScript/Node.js pattern. In Python, decorators and middleware are simpler and achieve the same thing.

---

### API Rate Limit Handling — Simplified & Visual

**What is rate limiting?**
LLM APIs (NVIDIA, OpenAI, etc.) set limits on how much you can use per minute:
- **RPM** = Requests Per Minute (e.g., max 60 API calls/min)
- **TPM** = Tokens Per Minute (e.g., max 100,000 tokens/min)

If you exceed these → you get a `429 Too Many Requests` error and your call fails.

**The 3 Levels Feynman Uses:**

```
Level 1: STRUCTURAL (Architecture Design)
═══════════════════════════════════════════

  BEFORE (Your pipeline — sequential):
  ┌───┐   ┌───┐   ┌───┐   ┌───┐   ┌───┐
  │ S │──▶│ R │──▶│ W │──▶│ C │──▶│ W │  = 5 serial API calls
  └───┘   └───┘   └───┘   └───┘   └───┘    over ~30-40 seconds
   6s      3s      6s      4s      6s       if one fails, you wait + retry

  AFTER (Feynman — parallel):
  ┌───┐──▶│ R │──┐
  │ Pi│           ├──▶│ W │──▶│ V │  = fewer total calls
  └───┘──▶│ Rev│──┘                    R + Rev run at SAME TIME
           (parallel)                  Total: ~18s instead of ~30s

  WHY THIS HELPS WITH RATE LIMITS:
  • Fewer sequential calls = less chance of hitting RPM limit
  • Smaller context per agent = less tokens per call = stays under TPM


Level 2: ORCHESTRATION (Pi Runtime — the traffic cop)
═════════════════════════════════════════════════════════

  Think of Pi as a traffic light for API calls:

  ┌─────────────────────────────────────┐
  │           Pi Orchestrator           │
  │                                     │
  │  Queue:  [Researcher] [Reviewer]    │
  │                                     │
  │  Rules:                             │
  │  • Max 2 concurrent LLM calls       │
  │  • If Agent A gets 429 → pause ALL  │
  │  • Priority: Researcher > Verifier  │
  │  • Track token usage across agents  │
  └─────────────────────────────────────┘

  This is "centralized dispatch" — one brain controlling all API access.
  Your pipeline has NO centralized control. Each agent calls the API
  independently and hopes for the best.


Level 3: APPLICATION (What happens when you DO hit a limit)
═══════════════════════════════════════════════════════════════

  When you get a 429 error:

  Attempt 1: Call API  ──▶  429 ERROR!
             wait 1 second + random(0-0.5s)    ← "jitter"

  Attempt 2: Call API  ──▶  429 ERROR!
             wait 2 seconds + random(0-1s)      ← doubles each time

  Attempt 3: Call API  ──▶  429 ERROR!
             wait 4 seconds + random(0-2s)      ← "exponential backoff"

  Attempt 4: Call API  ──▶  ✅ SUCCESS!

  WHY JITTER (random delay)?
  Without it: 10 agents all retry at exactly 2 seconds → instant 429 again
  With it:    agents retry at 1.7s, 2.3s, 1.9s, 2.5s → spread out = no storm

  CIRCUIT BREAKER:
  If you get 429 five times in a row:
  → STOP trying for 30 seconds (don't waste your remaining quota)
  → Then try ONE test call
  → If it works, resume normal operation
  → If it fails, wait another 30 seconds
```

**What you currently have:**
```python
time.sleep(2)  # This is NOT rate limiting. This is just... sleeping.
```

`time.sleep(2)` doesn't check if the API is actually rate-limiting you. It's a fixed delay regardless of whether you need it.

---

## 💡 Non-Blocking Synthesis — Simpler Alternatives

Feynman's Writer starts working before all evidence is in (because it reads from files as they're written). Simpler ways to get a similar effect in Python:

### Option A: Streaming with callbacks (Simplest)
```python
# Agent A finishes → immediately trigger Writer with partial data
# Agent B finishes → Writer gets the rest and revises
# No files needed — just event-driven callbacks
```

### Option B: Async gather with `as_completed`
```python
import asyncio

async def research_pipeline(topic):
    # Start both tasks
    tasks = [
        asyncio.create_task(researcher(topic)),
        asyncio.create_task(reviewer(topic)),
    ]
    
    results = []
    # Process results AS THEY ARRIVE, not waiting for all
    for coro in asyncio.as_completed(tasks):
        result = await coro
        results.append(result)
        # Could start partial synthesis here!
    
    # Then write the full report with all results
    report = await writer(results)
```

### Option C: Simple queue (Most pragmatic)
```python
from queue import Queue
import threading

result_queue = Queue()

# Each agent puts results in the queue when done
# Writer thread reads from queue and builds report incrementally
```

**My preference for now:** Option B — async with `as_completed`. Clean, Pythonic, no external dependencies.

---

## 📋 Action Items

- [ ] Research optimal thinking level detection methods (avoid trial-and-error)
- [ ] Add integrity commandments to Writer prompt
- [ ] Design "Advanced Config" UI section for thinking levels + context scope
- [ ] Implement basic exponential backoff with jitter (replace `time.sleep()`)
- [ ] Prototype parallel agent dispatch with `asyncio`
- [ ] Decide: file-based state or keep in-memory (leaning toward optional later)

---

*Last updated: 2026-08-16*
