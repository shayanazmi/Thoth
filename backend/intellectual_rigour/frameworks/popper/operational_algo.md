# Operational Algorithm: Popperian Falsification Audit

```text
INPUT: Research Report Markdown, Topic, Target Claims, Extracted Sources
OUTPUT: Structured ThinkerOutput & ReviewArtifact

STEP 1: CLAIM & CONJECTURE EXTRACTION
  - Identify primary empirical conclusions, causal claims, and quantitative performance assertions.
  - Separate descriptive background summaries from falsifiable conjectures.

STEP 2: FORMALIZATION OF POTENTIAL FALSIFIERS
  - For each substantive claim C, formulate:
      Falsifier(C) = "What specific observable outcome, dataset, or experiment would unambiguously refute C?"
  - If no conceivable empirical observation can refute C, flag as `UNFALSIFIABLE_SHIELD` (Severity: CRITICAL/MAJOR).

STEP 3: RISKY PREDICTION INSPECTION
  - Determine if the research relies on bold, risky predictions or safe retrospective curve-fitting.
  - Assess if predictions ruling out alternative mechanisms were tested.

STEP 4: SEARCH FOR CONTRADICTORY EVIDENCE & COUNTEREXAMPLES
  - Query provided source data and literature for:
      a) Incompatible observations or benchmark regressions.
      b) Edge cases where the proposed mechanism breaks down.
      c) Negative results ignored in discussion.

STEP 5: AD-HOC IMMUNIZATION DETECTION
  - Inspect whether limitations or failure modes are dismissed using ad-hoc excuses (e.g. "it only fails due to unmeasured noise", post-hoc hyperparameter tuning without cross-validation).

STEP 6: CORROBORATION VS VERIFICATION AUDIT
  - Ensure the report does not claim to have "proven" or "verified" a universal theory; ensure findings are framed as robust corroboration under tested conditions.

STEP 7: CONTEXT-FIRST WITHHOLDING & VERDICT ASSIGNMENT
  - If a claim is testable but necessary validation benchmarks are missing from context:
      verdict = INSUFFICIENT_CONTEXT
      recommendation = WITHHELD_PENDING_CONTEXT
      required_context = [exact experimental data / dataset needed]
  - If clear fatal flaws or unfalsifiable shields exist:
      verdict = MATERIAL_OBJECTION
  - If all claims are sharply formulated, severely tested, and corroborated without ad-hoc shields:
      verdict = NO_MATERIAL_OBJECTION
```
