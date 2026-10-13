# Operational Algorithm: Humean Inference & Causal Audit

```text
INPUT: Research Claims C, Empirical Evidence E
OUTPUT: Structured ThinkerOutput & ReviewArtifact

FOR each substantive claim C_i:

STEP 1: CLAIM DECOMPOSITION & STRATIFICATION
  - Separate raw observations from inductive interpretations.
  - Assign Epistemic Distance Level (0 to 4):
      - Level 0: Direct raw observation / measurement.
      - Level 1: Reported dataset / recorded metric.
      - Level 2: Statistical association / correlation.
      - Level 3: Inferred causal mechanism.
      - Level 4: Universal or necessary law.

STEP 2: INFERENTIAL JUMP IDENTIFICATION
  - Pinpoint the exact location where the text transitions across epistemic levels (e.g. from Level 2 correlation to Level 3 causal assertion).

STEP 3: CAUSALITY ATTACK & COUNTER-HYPOTHESES
  - For every asserted relation A -> B, systematically construct alternative explanations:
      1. Reverse Causality: B -> A
      2. Common Confounder: C -> A and C -> B
      3. Selection Bias / Sampling Artifact: A and B are correlated only in conditioned sample S
      4. Coincidence / Noise / Data Dredging
      5. Measurement Artifact

STEP 4: NECESSITY & INDUCTION AUDIT
  - Distinguish observed constant conjunction from claimed necessary connection.
  - Determine what justifies extending observed correlation out-of-sample or into future regimes.

STEP 5: EPISTEMIC RE-CALIBRATION
  - Re-write overconfident assertions into calibrated probabilistic language:
      - Certainty -> Probability
      - Necessity -> Observed regularity under specified conditions
      - Universal Law -> Bounded empirical association

STEP 6: CONTEXT-FIRST ASSIGNMENT & OUTPUT
  - If instrumental variables, randomized control data, or confounder adjustments are missing from context:
      verdict = INSUFFICIENT_CONTEXT
      recommendation = WITHHELD_PENDING_CONTEXT
  - If unaddressed confounders or ungrounded causal leaps dominate the conclusions:
      verdict = MATERIAL_OBJECTION
  - If causal inferences are rigorously controlled and uncertainty is properly calibrated:
      verdict = NO_MATERIAL_OBJECTION
```
