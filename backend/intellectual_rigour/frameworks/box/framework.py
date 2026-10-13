from typing import Dict, Any, Optional, List
import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.agents import llm, safe_extract_json, strip_chain_of_thought
from backend.intellectual_rigour.models import (
    ReviewRequest,
    ReviewArtifact,
    ThinkerOutput,
    CritiqueFinding,
    ReasoningSpec,
)
from backend.intellectual_rigour.frameworks.base import BaseThinkerFramework

logger = logging.getLogger("ThothIntellectualRigour.Box")

BOX_SYSTEM_PROMPT = """You are executing the George Box (Model Criticism & Residual Diagnostics) Reasoning Framework.
Your purpose is to conduct a rigorous diagnostic audit of quantitative models, machine learning architectures, statistical predictions, and simulations.

Core Epistemic Principles:
1. All Models Are Wrong, Some Are Useful: Evaluate whether a model's deliberate simplifications destroy its intended practical utility.
2. Residual & Error Structure: Check whether prediction errors are random noise (good) or exhibit structured, systematic bias (model misspecification).
3. Parameter Perturbation & Sensitivity: Assess whether slight shifts in input distributions or hyperparameter settings cause catastrophic performance collapse.
4. Boundary Mapping: Explicitly delineate where the model transitions from reliable utility to uncalibrated failure.
5. Parsimony (Occam's Razor): Challenge unnecessary model complexity when simpler baseline models achieve equivalent out-of-sample performance.

CRITICAL OPERATING RULES:
- NEVER MANUFACTURE CRITICISM: If the model provides clean residuals, demonstrates stability under perturbation, and clearly bounds its domain of utility, return verdict "NO_MATERIAL_OBJECTION".
- CONTEXT-FIRST RULE: If judging model adequacy requires missing residual breakdowns, sensitivity curves, or out-of-distribution validation data, return verdict "INSUFFICIENT_CONTEXT" and set required_context with recommendation "WITHHELD_PENDING_CONTEXT".
- NO ARCHAIC PERSONA ROLEPLAY: Write in objective, precise analytical prose.

Output strictly valid JSON matching this schema:
{{
  "verdict": "MATERIAL_OBJECTION" | "NO_MATERIAL_OBJECTION" | "INSUFFICIENT_CONTEXT" | "INSUFFICIENT_EVIDENCE" | "OUTSIDE_SCOPE" | "UNRESOLVED",
  "has_material_objections": true | false,
  "critiques": [
    {{
      "target_claim_or_method": "The exact model, statistical estimator, or predictive architecture under audit",
      "critique_type": "FATAL_FLAW" | "UNSUPPORTED_INFERENCE" | "UNFALSIFIABLE_SHIELD" | "CONCEPTUAL_AMBIGUITY" | "BOUNDARY_LIMIT" | "SOUND_NO_OBJECTION",
      "severity": "CRITICAL" | "MAJOR" | "MODERATE" | "MINOR" | "INFORMATIONAL",
      "blocking": true | false,
      "problem": "Precise explanation of the structured residual, sensitivity fragility, or boundary failure",
      "why_it_matters": "Impact on model reliability and fitness for intended purpose",
      "evidence_or_counterexample": "Specific failure regime or demonstrated sensitivity breakdown",
      "required_context": "Missing residual data or perturbation plots needed before prescribing fixes, or empty",
      "recommendation": "Concrete model simplification, transformation, or boundary constraint, or WITHHELD_PENDING_CONTEXT",
      "confidence": 0.9,
      "provenance_rule": "Box: Residual Diagnostics / Model Misspecification / Sensitivity Stress-Test / Boundary Mapping"
    }}
  ],
  "unresolved_questions": ["1-2 diagnostic or sensitivity questions"],
  "model_stress_diagnostics": ["1-2 concrete perturbation or residual stress tests"],
  "executive_summary": "2-3 sentence model criticism verdict",
  "epistemic_notes": "Distinction between Boxian statistical diagnostics and modern machine learning calibration"
}}
Output ONLY the JSON object without markdown code fences or conversational commentary."""

BOX_HUMAN_PROMPT = """Research Topic: {topic}

Target Scope: {target_scope} {section_focus}

Research Material to Audit:
{content}

Perform the Box Model-Criticism & Diagnostic Audit now."""

box_prompt_template = ChatPromptTemplate.from_messages([
    ("system", BOX_SYSTEM_PROMPT),
    ("human", BOX_HUMAN_PROMPT),
])

box_chain = box_prompt_template | llm | StrOutputParser()

class BoxFramework(BaseThinkerFramework):
    id = "box"
    name = "George Box"
    tradition = "Iterative Statistical Model Building & Residual Diagnostics"
    epistemic_role = "Model Criticism & Boundary Diagnostic Critic"
    section_heading = "### 🏛️ Philosophical Review: George Box (Model Criticism & Boundaries)"

    spec = ReasoningSpec(
        id="box",
        thinker_name="George Box",
        tradition="Iterative Statistical Model Building & Residual Diagnostics",
        epistemic_role="Model Criticism & Boundary Diagnostic Critic",
        applies_to=["statistical_models", "ml_architectures", "quantitative_simulations", "predictive_algorithms"],
        does_not_apply_to=["pure_deductive_logic", "normative_ethics", "qualitative_historical_narratives"],
        fidelity="documented"
    )

    def _invoke_chain(self, inputs: Dict[str, Any]) -> str:
        return box_chain.invoke(inputs)

    def review(
        self,
        request: ReviewRequest,
        report_text: str,
        topic: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> ReviewArtifact:
        if not report_text or not report_text.strip():
            empty_hash = self.compute_source_hash(report_text)
            empty_markdown = f"""<!-- intellectual-rigour:start framework="{self.id}" source_hash="{empty_hash}" -->
{self.section_heading}

> **Epistemic Verdict**: `OUTSIDE_SCOPE` (No substantive research content provided to audit).
<!-- intellectual-rigour:end -->"""
            return ReviewArtifact(
                framework_id=self.id,
                target_section_title=self.section_heading,
                operation="append_section",
                formatted_markdown=empty_markdown,
                source_hash=empty_hash,
                metadata={"verdict": "OUTSIDE_SCOPE", "critiques_count": 0}
            )

        source_hash = self.compute_source_hash(report_text)
        target_scope = request.target.scope
        section_focus = f"(Focusing on section: {request.target.section_title})" if request.target.section_title else ""

        try:
            raw_response = self._invoke_chain({
                "topic": topic or "Autonomous Research Investigation",
                "target_scope": target_scope,
                "section_focus": section_focus,
                "content": report_text[:14000]
            })
            cleaned_text = strip_chain_of_thought(raw_response)
            parsed = safe_extract_json(cleaned_text, default={})
        except Exception as e:
            logger.error(f"[BOX FRAMEWORK ERROR] LLM execution failed: {e}")
            parsed = {
                "verdict": "UNRESOLVED",
                "has_material_objections": False,
                "critiques": [],
                "unresolved_questions": [f"Execution error during Box model audit: {e}"],
                "executive_summary": f"Model audit could not complete due to execution failure: {e}",
                "epistemic_notes": "Service degradation."
            }

        verdict = parsed.get("verdict", "NO_MATERIAL_OBJECTION")
        has_objections = parsed.get("has_material_objections", False)
        exec_summary = parsed.get("executive_summary", "Model diagnostic audit complete.")
        critiques_raw = parsed.get("critiques", [])
        unresolved_q = parsed.get("unresolved_questions", [])
        diagnostics = parsed.get("model_stress_diagnostics", [])
        epistemic_notes = parsed.get("epistemic_notes", "Analysis applies Box iterative model criticism.")

        critique_items: List[CritiqueFinding] = []
        for c in critiques_raw:
            try:
                critique_items.append(CritiqueFinding(**c))
            except Exception:
                pass

        formatted_md = self._render_markdown(
            source_hash=source_hash,
            verdict=verdict,
            executive_summary=exec_summary,
            critiques=critique_items,
            unresolved_questions=unresolved_q,
            diagnostics=diagnostics,
            epistemic_notes=epistemic_notes
        )

        return ReviewArtifact(
            framework_id=self.id,
            target_section_title=self.section_heading,
            operation="append_section",
            formatted_markdown=formatted_md,
            source_hash=source_hash,
            metadata={
                "verdict": verdict,
                "has_material_objections": has_objections,
                "critiques_count": len(critique_items),
                "source_hash": source_hash
            }
        )

    def _render_markdown(
        self,
        source_hash: str,
        verdict: str,
        executive_summary: str,
        critiques: List[CritiqueFinding],
        unresolved_questions: List[str],
        diagnostics: List[str],
        epistemic_notes: str
    ) -> str:
        status_icons = {
            "MATERIAL_OBJECTION": "🔴 **MATERIAL OBJECTION**",
            "NO_MATERIAL_OBJECTION": "🟢 **NO MATERIAL OBJECTION (Model is Parsimonious & Well-Calibrated)**",
            "INSUFFICIENT_CONTEXT": "🟡 **INSUFFICIENT CONTEXT (Withheld Pending Residual Diagnostics)**",
            "INSUFFICIENT_EVIDENCE": "🟠 **INSUFFICIENT EVIDENCE**",
            "OUTSIDE_SCOPE": "⚪ **OUTSIDE MODELING SCOPE**",
            "UNRESOLVED": "⚠️ **UNRESOLVED**"
        }
        verdict_str = status_icons.get(verdict, f"**{verdict}**")

        lines = [
            f"<!-- intellectual-rigour:start framework=\"{self.id}\" source_hash=\"{source_hash}\" -->",
            self.section_heading,
            "",
            f"> **Epistemic Verdict**: {verdict_str}",
            f"> *Source Hash*: `{source_hash}` · *Framework*: George Box (Model Criticism & Residual Diagnostics)",
            "",
            f"{executive_summary}",
            ""
        ]

        if critiques:
            lines.append("#### Model Diagnostics & Boundary Critiques")
            for idx, c in enumerate(critiques, 1):
                severity_badge = f"`{c.severity}`"
                blocking_badge = " · **BLOCKING**" if c.blocking else ""
                lines.append(f"##### {idx}. {c.target_claim_or_method} ({severity_badge}{blocking_badge})")
                lines.append(f"- **Problem**: {c.problem}")
                lines.append(f"- **Epistemic Impact**: {c.why_it_matters}")
                if c.evidence_or_counterexample:
                    lines.append(f"- **Failure Regime / Residual Deviation**: {c.evidence_or_counterexample}")
                if c.required_context:
                    lines.append(f"- **Required Context**: {c.required_context}")
                if c.recommendation:
                    lines.append(f"- **Remediation**: {c.recommendation}")
                lines.append(f"- *Provenance Rule*: `{c.provenance_rule}`")
                lines.append("")

        if diagnostics:
            lines.append("#### Recommended Model Stress-Tests")
            for d in diagnostics:
                lines.append(f"- 📊 {d}")
            lines.append("")

        if unresolved_questions:
            lines.append("#### Open Modeling & Calibration Questions")
            for q in unresolved_questions:
                lines.append(f"- ❓ {q}")
            lines.append("")

        if epistemic_notes:
            lines.append(f"> [!NOTE]\n> **Epistemic Grounding**: {epistemic_notes}")
            lines.append("")

        lines.append("<!-- intellectual-rigour:end -->")
        return "\n".join(lines)
