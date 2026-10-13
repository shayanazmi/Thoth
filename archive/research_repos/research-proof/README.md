# Research Proof

[![Claude Code Marketplace](https://img.shields.io/badge/Claude%20Code-marketplace-5A32A3?logo=anthropic&logoColor=white)](#claude-code-plugin) [![skills.sh](https://skills.sh/b/tonyblu331/research-proof)](https://skills.sh/tonyblu331/research-proof)

Pressure-test research claims with falsifiable evidence plans, adversarial checks, frozen verifiers, evidence certainty checks, and proof ledgers.

## Why this exists

Agents are too eager to implement.

Research Proof forces them to state the claim, freeze the verifier, name rejection gates, charge hidden costs, and update a proof ledger before moving forward.

The mental model behind Research Proof is simple: treat every promising idea as a claim under test. Borrow the habits that strong research teams use across AI, medicine, mathematics, engineering, and design: freeze the verifier, separate evidence from interpretation, search for counterexamples, charge hidden costs, and only upgrade confidence when the claim survives transfer pressure. References shape the method; they are never treated as proof of a user claim.

![Research Proof image generation concept](assets/research-proof-imagegen.png)

## Release 1.3.0

This release keeps the skill compact while making the proof path easier to follow.

Highlights:

- Makes the selected proof method and next method-specific moves explicit.
- Keeps compact and schema-style answers from dropping raw evidence or rejected shortcuts.
- Adds practical eval-harness guidance for reusable helpers instead of one-off scripts.
- Keeps status language tied to the evidence in the answer.
- Updates the Claude Code plugin to `1.3.0`.

The references are intentionally plain: proof ladders, causal attribution, live-source review, clinical evidence review, design research, cross-domain transfer, and eval harness structure.

See [`CHANGELOG.md`](CHANGELOG.md) for release notes.

## Install

```powershell
npx skills add tonyblu331/research-proof --skill research-proof
```

Global install:

```powershell
npx skills add tonyblu331/research-proof --skill research-proof -g
```

List available skills before installing:

```powershell
npx skills add tonyblu331/research-proof --list
```

Manual install:

```powershell
git clone https://github.com/tonyblu331/research-proof.git
```

Then copy `skills/research-proof` into your agent's skills directory.

## Claude Code Plugin

This repo is a Claude Code marketplace. Install it with:

```powershell
claude plugin marketplace add tonyblu331/research-proof
claude plugin install research-proof-plugin@research-proof
```

Invoke it with:

```text
/research-proof-plugin:research-proof
```

The plugin wrapper lives here:

```text
.claude-plugin/marketplace.json
plugins/research-proof-plugin/
  .claude-plugin/plugin.json
  skills/research-proof/
```

Local plugin test:

```powershell
claude plugin marketplace add .\
claude --plugin-dir .\plugins\research-proof-plugin
```

Optional local checks:

```powershell
node .\tools\validate-research-skill.mjs
claude plugin validate .
claude plugin validate .\plugins\research-proof-plugin
```

## Use It For

Use Research Proof when a claim is promising but still vague:

```text
Use research-proof to pressure-test this claim: our agent loop can improve a prompt library overnight without human review.
```

Good fits:

- research roadmaps
- benchmark reviews
- proof ladders
- cross-domain mathematical transfer
- evaluator-gated loops
- research TDD scenarios
- clinical or intervention evidence questions
- systematic reviews and evidence-certainty checks
- causal inference and observational-data claims
- mathematical innovation by borrowing invariants, constructions, or proof tools from distant fields
- SIGGRAPH-style artifact, rendering, simulation, and perceptual-system claims
- tool-grounded scientific workflows and live-source research claims
- clinical AI reporting, calibration, validation, and deployment-readiness claims
- design research and prototype-readiness claims
- research-program strategy and funding decisions
- adversarial follow-up tests

## Tiny Before / After Examples

### Vague benchmark claim

Before:

```text
Our new retrieval strategy beats the baseline.
```

After:

```text
Claim: On frozen dataset D, candidate retrieval C beats baseline B only if answer accuracy improves by at least 5 points, p95 latency stays under budget, and no added manual labeling is required.
Rejection Gates: Reject if the evaluator changes, wins only on visible examples, hides latency cost, or fails a held-out query family.
```

### Messy research paper claim

Before:

```text
This paper proves the method generalizes.
```

After:

```text
Claim: The paper supports generalization only for domain D, metric M, and comparison B used in the study.
Enemy Terms: Dataset leakage, weak baselines, missing ablations, narrow distribution, and author interpretation separated from measured results.
```

### Agent loop claim

Before:

```text
The agent can improve the repo by looping on issues overnight.
```

After:

```text
Verifier Boundary: Freeze issues, tests, budgets, writable files, and review authority before the loop starts.
Rejection Gates: Reject if the agent edits the verifier, creates duplicate work, exceeds budget, needs manual cleanup, or cannot reproduce the ledger from evidence.
```

## What It Produces

Research Proof forces the agent to define:

```text
Claim
Verifier Boundary
Baseline / Candidate Family
Current Evidence
Enemy Terms
Rejection Gates
Proof Ladder / Transfer Path
Verdict
Proof Ledger Decision
Next Pressure
```

Evidence is labeled as `PROVEN`, `SUPPORTED`, `REJECTED`, or `OPEN`.

## Not a magic proof machine

Repo evidence is not universal proof. Research Proof improves research discipline by making the claim, verifier, rejection gates, hidden costs, and ledger explicit, but transfer still needs held-out or production-style validation.

That honesty is part of the product.

## Quick Example

Messy claim:

```text
Our autonomous loop can improve a prompt library overnight without human review.
```

Research Proof rewrite:

```text
Claim
For prompt set D and baseline B, candidate loop C wins only if held-out task score improves by +5% while latency, token cost, regressions, and human review stay within budget.

Verifier Boundary
The evaluator, held-out tasks, scoring rubric, and regression set are frozen before the loop starts. The candidate can edit prompts only. It cannot inspect held-out answers, change tests, widen budgets, or mark its own outputs as accepted.

Rejection Gates
Reject if the candidate changes the evaluator, fails regression, exceeds token budget, improves only visible tasks, or requires manual cleanup.

Proof Ledger Decision
OPEN until it wins the frozen harness and survives transfer.

Next Pressure
Run a transfer test on a new prompt family with the same scoring rules.
```

See [`examples/fuzzy-claim-proof-ledger.md`](examples/fuzzy-claim-proof-ledger.md) for the full worked example.

## Distribution

This repository ships the same skill through Claude Code plugins and the open `skills` CLI. The source of truth is `skills/research-proof`; the plugin skill directory is a distribution copy kept in sync by the repo checks.

- Source: [github.com/tonyblu331/research-proof](https://github.com/tonyblu331/research-proof)
- Releases: [github.com/tonyblu331/research-proof/releases](https://github.com/tonyblu331/research-proof/releases)

## Repository Layout

```text
assets/
examples/
plugins/research-proof-plugin/
skills/research-proof/
  SKILL.md
  evals/evals.json
  references/
tools/
  lib/
  validate-research-skill.mjs
.github/
```

## License

MIT
