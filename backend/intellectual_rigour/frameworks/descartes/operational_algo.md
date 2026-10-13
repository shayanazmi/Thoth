# Operational Algorithm: Cartesian First-Principles & Decomposition Audit

```text
INPUT: Complex Research Problem R, Stated Propositions P
OUTPUT: Structured ThinkerOutput & ReviewArtifact

STEP 1: UNCHECKED ASSUMPTION SUSPENSION
  - Identify and temporarily bracket all inherited domain conventions, unproven literature assumptions, and common-sense heuristics.

STEP 2: ATOMIC DECOMPOSITION
  - Deconstruct complex claims R into atomic constituent propositions:
      R -> {r_1, r_2, ..., r_n}
  - Continue dividing until each sub-proposition cannot be further decomposed without loss of meaning.

STEP 3: PRIMITIVE TAXONOMY & CLASSIFICATION
  - Classify each r_i into one of four epistemic states:
      - Established: Empirically verified or mathematically proven.
      - Inferred: Deduced from established premises.
      - Assumed: Unproven hypothesis or inherited premise.
      - Unknown: Unclear or unmeasured.

STEP 4: DEPENDENCY DAG RECONSTRUCTION
  - Map propositions into a strict directed acyclic graph (DAG):
      Foundations (Level 0) -> Intermediate Inferences (Level 1) -> Final Claims (Level 2+)
  - Detect hidden dependencies and circular feedback loops.

STEP 5: SUBTRACTION STRESS-TEST
  - For each unproven assumption A_k in the foundation:
      "If A_k is false or removed, does the core conclusion still hold?"
  - If a core conclusion depends critically on an unproven assumption without acknowledgment, flag as `FATAL_FLAW` or `UNSUPPORTED_INFERENCE`.

STEP 6: MINIMAL RECONSTRUCTION
  - Assemble the simplest, most parsimonious deductive path that preserves valid conclusions while stripping away extraneous speculative scaffolding.

STEP 7: CONTEXT-FIRST ASSIGNMENT & OUTPUT
  - If foundational mathematical derivations or axiomatic assumptions are missing from context:
      verdict = INSUFFICIENT_CONTEXT
      recommendation = WITHHELD_PENDING_CONTEXT
  - If an unproven assumption fatally undermines downstream conclusions:
      verdict = MATERIAL_OBJECTION
  - If reasoning decomposes into rock-solid primitives and clear dependencies:
      verdict = NO_MATERIAL_OBJECTION
```
