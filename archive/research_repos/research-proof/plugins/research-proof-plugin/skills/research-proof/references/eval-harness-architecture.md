# Eval Harness Architecture

Use when adding or changing eval cases, graders, artifact checks, or metric harnesses. Goal: reproducible evidence without heavy machinery.

```text
case registry -> runner -> artifacts -> graders -> aggregate -> short report
```

## Design Principles

- One case schema: input, expected artifacts, grading criteria, limits, and Measurement Boundary.
- Separate roles: runner executes; artifact store records; grader scores; reporter summarizes.
- Structured evidence first: JSON, CSV, snapshots, diffs, metrics, typed traces. Prose comes after scoring.
- Shared assertions and domain contracts before local code.
- Fail closed on missing artifacts, malformed rows, stale refs, parser errors, or contradictory statuses.
- Small public report; raw detail stays in machine-readable files.

## Helper Selection

```text
One case only? keep it in the case/fixture.
Existing assertion/schema/adapter covers it? reuse it.
Same evidence shape repeats? extend Shared domain contracts.
Same check repeats? extend assertions.
Repeated domain execution/normalization? add or extend an adapter.
```

Prefer a named shared contract over a generic helper. Extract only when the next case can reuse it.

## Recommended Modules

```text
evals/cases.json          # source of truth
evals/fixtures/           # tiny fixtures
tools/lib/
  case-registry.mjs       # load/filter/validate cases
  schemas.mjs             # case, artifact, result shapes
  runner.mjs              # execute one case/variant
  artifact-store.mjs      # paths, manifests, safe writes
  logger.mjs              # quiet/human/jsonl events
  assertions.mjs          # reusable gates
  domain-contracts/       # source, claim, diff, command, rubric, metric shapes
  evidence-ref.mjs        # resolve artifact refs
  contradiction-scan.mjs  # status/report consistency
  scorer.mjs              # gates -> score/verdict
  report-writer.mjs       # compact summaries
  adapters/               # domain-specific measurement
```

Core modules stay domain-agnostic; adapters translate a domain into the same case/artifact/result/scoring flow.

## Helper Contracts

```js
registry.defineCase({ id, tags, input, expectedArtifacts, assertions, limits, measurementBoundary })
artifacts.require(caseId, refs)
artifacts.write(ref, value)
assertions.fromContract(contractName, checks)
assertions.compose(...checks)
adapter.define({ family, normalize(input), run(ctx), artifacts(result), assertions() })
```

Case registry validates schema and rejects unknown fields unless versioned. Artifact store owns paths, manifests, cleanup, and workspace safety. Logger emits structured events instead of ad-hoc terminal prints. Adapters normalize, run/observe, emit artifacts, and expose assertions; the shared scorer owns final verdicts.


## Discovery-to-Acceptance Cut

Do not preserve exploratory scaffolding as the product verifier. Once a discovery loop finds the useful signal, rewrite the default path around the smaller acceptance contract:

```text
exploratory studies -> normalized proof facts -> gates -> compact artifacts
```

Use this split:

| Exploratory scaffolding | Acceptance verifier |
| --- | --- |
| narrative reports, broad oracles, temporary microscopes, roadmap notes | normalized fact capture, named gates, compact summaries |
| useful while finding a cause | useful in CI/default verification |
| archived or opt-in debug after convergence | default path after convergence |

A default verifier should answer: “does the current implementation meet the known gates?” not “how did we discover the gates?” If a report branch exists only to explain history, archive it. If it answers a direct gate, reduce it to a fact reader or assertion.

Preferred shape:

```js
const facts = normalizeProofFacts( raw );
const gates = evaluateProofGates( facts );
assertGates( gates );
writeCompactSummary( gates );
```

Reject rewrites that merely rename old reports, keep giant current-evidence objects, or let markdown become the source of truth.

## Evidence Reference Resolver

Resolve claims to structured evidence, not prose:

```js
resolveEvidenceRef("results.json#/cases/alpha/verdict")
resolveEvidenceRef("scores.csv#row=17")
```

Missing file, missing row/key, wrong type, stale run, or prose-only reference keeps the claim `OPEN`.

## Shared domain contracts

Start each eval family from a shared JSON contract and extend only what the scorer needs:

```text
prompt/rubric: prompt, variant, sampling, rubric version, rows
file edit: pre/post manifest, diff, changed paths, required/forbidden edits
command/tool: cwd, env, stdin/out/err, status, side effects, cleanup
benchmark: baseline, target, environment, repetitions, threshold, variance policy
source review: locator, retrieved date, evidence spans, claim links, quality flags
causal claim: cause, effect, context, confounders, counterfactual basis, alternatives
proof check: claim, assumptions, checker result, unresolved gaps
prototype: required flows, traces, snapshots, acceptance gates, open risks
```

## Contradiction Scanner

Scan structured states, manifests, and summaries together:

```text
OPEN evidence + closed headline
unsupported artifact ref + accepted verdict
failed required check + pass summary
unavailable path + active-feature label
```

## Measurement Boundary

Every metric records:

```text
measures: observed path/behavior
does_not_measure: outside scope
proxy_for: optional target
closure_rule: evidence that would make it sufficient
```

If proxy and target disagree, keep both and mark `OPEN` until a discriminator explains the gap. For subjective evals, closure requires structured rubric rows, verifier results, assumptions, traces, acceptance gates, or risk lists; prose alone is not closure.

## Artifact Policy

Default: run manifest, normalized inputs, output when relevant, structured scores, failure evidence, compact report. Opt-in/failure-only: full traces, screenshots, large logs, profiling files, repeated intermediate states. Keep large generated outputs out of repo.

## Performance Defaults

Parse once, pass typed objects, index repeated lookups, stream large JSONL/CSV, cache immutable fixtures by content hash, document bounded O(n²), and keep scoring separate from report writing.

## Adding or Changing an Eval

1. Add/update the case in the registry.
2. Declare artifacts, assertions, limits, and Measurement Boundary.
3. Reuse helpers/contracts before a new helper.
4. Put domain-specific behavior in an adapter.
5. Add the smallest fixture that exposes the behavior.
6. Run the smallest relevant check.
7. Update reports only after scorer output exists.

Tiny reuse examples: file-edit regression uses the `file edit` contract; source-review uses the `source review` contract and `evidence-ref`.

## Review Checklist

- One case shape? Shared contract or adapter reused?
- Grader reads structured artifacts, not prose?
- Logs quiet and structured by default?
- Artifacts necessary, named, manifested?
- Metric boundary explicit?
- Missing/stale evidence fails closed?
- Can `OPEN` become closed-looking elsewhere?
- Is this simpler than the previous version?
