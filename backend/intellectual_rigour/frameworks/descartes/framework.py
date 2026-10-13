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

logger = logging.getLogger("ThothIntellectualRigour.Descartes")

DESCARTES_SYSTEM_PROMPT = """You are executing the René Descartes (First-Principles & Foundational Decomposition) Reasoning Framework.
Your purpose is to conduct a rigorous analytical decomposition of complex research claims, architectures, models, and proofs.

Core Epistemic Principles:
1. Methodological Doubt & Suspension: Temporarily bracket inherited conventions, industry dogmas, and unstated intuitions.
2. Atomic Decomposition: Divide complex composite claims into distinct, manageable atomic primitive propositions.
3. Primitive Epistemic State: Classify primitives strictly into Established, Inferred, Assumed, or Unknown.
4. Dependency Ordering: Trace the structural sequence from foundational premises to intermediate steps and final conclusions.
5. Assumption Subtraction Stress-Test: Test whether core conclusions survive when key unproven assumptions are stripped away.

CRITICAL OPERATING RULES:
- NEVER MANUFACTURE CRITICISM: If the research rests on clear, verified primitives with robust dependency logic and minimal unnecessary complexity, return verdict "NO_MATERIAL_OBJECTION".
- CONTEXT-FIRST RULE: If judging foundational validity requires missing mathematical derivations or physical constants, return verdict "INSUFFICIENT_CONTEXT" and set required_context with recommendation "WITHHELD_PENDING_CONTEXT".
- NO ARCHAIC PERSONA ROLEPLAY: Write in objective, precise analytical prose.

Output strictly valid JSON matching this schema:
{{
  "verdict": "MATERIAL_OBJECTION" | "NO_MATERIAL_OBJECTION" | "INSUFFICIENT_CONTEXT" | "INSUFFICIENT_EVIDENCE" | "OUTSIDE_SCOPE" | "UNRESOLVED",
  "has_material_objections": true | false,
  "critiques": [
    {{
      "target_claim_or_method": "The exact compound claim, dependency link, or foundational assumption under audit",
      "critique_type": "FATAL_FLAW" | "UNSUPPORTED_INFERENCE" | "UNFALSIFIABLE_SHIELD" | "CONCEPTUAL_AMBIGUITY" | "BOUNDARY_LIMIT" | "SOUND_NO_OBJECTION",
      "severity": "CRITICAL" | "MAJOR" | "MODERATE" | "MINOR" | "INFORMATIONAL",
      "blocking": true | false,
      "problem": "Precise explanation of the hidden dependency, fragile assumption, or decomposition defect",
      "why_it_matters": "Impact on foundational reliability and conclusion survival",
      "evidence_or_counterexample": "Demonstration of conclusion collapse when assumption is subtracted",
      "required_context": "Missing foundational data needed before prescribing fixes, or empty",
      "recommendation": "Concrete minimal reconstruction or assumption decoupling, or WITHHELD_PENDING_CONTEXT",
      "confidence": 0.9,
      "provenance_rule": "Descartes: Methodological Doubt / Atomic Decomposition / Dependency DAG / Assumption Subtraction"
    }}
  ],
  "unresolved_questions": ["1-2 foundational first-principles questions"],
  "primitive_foundations": ["1-2 verified atomic primitives"],
  "executive_summary": "2-3 sentence first-principles and structural verdict",
  "epistemic_notes": "Distinction between Cartesian foundationalism and modern modular system decomposition"
}}
Output ONLY the JSON object without markdown code fences or conversational commentary."""

DESCARTES_HUMAN_PROMPT = """Research Topic: {topic}

Target Scope: {target_scope} {section_focus}

Research Material to Audit:
{content}

Perform the Cartesian First-Principles & Decomposition Audit now."""

descartes_prompt_template = ChatPromptTemplate.from_messages([
    ("system", DESCARTES_SYSTEM_PROMPT),
    ("human", DESCARTES_HUMAN_PROMPT),
])

descartes_chain = descartes_prompt_template | llm | StrOutputParser()

class DescartesFramework(BaseThinkerFramework):
    id = "descartes"
    name = "René Descartes"
    tradition = "Rationalist Foundationalism & Methodological Decomposition"
    epistemic_role = "First-Principles & Structural Decomposition Critic"
    section_heading = "### 🏛️ Philosophical Review: René Descartes (First-Principles & Decomposition)"

    spec = ReasoningSpec(
        id="descartes",
        thinker_name="René Descartes",
        tradition="Rationalist Foundationalism & Methodological Decomposition",
        epistemic_role="First-Principles & Structural Decomposition Critic",
        applies_to=["complex_systems", "theoretical_architectures", "mathematical_proofs", "pipelines", "causal_chains"],
        does_not_apply_to=["unstructured_empirical_observations", "purely_descriptive_chronologies", "aesthetic_judgments"],
        fidelity="documented"
    )

    def _invoke_chain(self, inputs: Dict[str, Any]) -> str:
        return descartes_chain.invoke(inputs)

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
            logger.error(f"[DESCARTES FRAMEWORK ERROR] LLM execution failed: {e}")
            parsed = {
                "verdict": "UNRESOLVED",
                "has_material_objections": False,
                "critiques": [],
                "unresolved_questions": [f"Execution error during Cartesian audit: {e}"],
                "executive_summary": f"Decomposition audit could not complete due to execution failure: {e}",
                "epistemic_notes": "Service degradation."
            }

        verdict = parsed.get("verdict", "NO_MATERIAL_OBJECTION")
        has_objections = parsed.get("has_material_objections", False)
        exec_summary = parsed.get("executive_summary", "First-principles structural audit complete.")
        critiques_raw = parsed.get("critiques", [])
        unresolved_q = parsed.get("unresolved_questions", [])
        primitive_foundations = parsed.get("primitive_foundations", [])
        epistemic_notes = parsed.get("epistemic_notes", "Analysis applies Cartesian foundational decomposition.")

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
            primitive_foundations=primitive_foundations,
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
        primitive_foundations: List[str],
        epistemic_notes: str
    ) -> str:
        status_icons = {
            "MATERIAL_OBJECTION": "🔴 **MATERIAL OBJECTION**",
            "NO_MATERIAL_OBJECTION": "🟢 **NO MATERIAL OBJECTION (Structurally Sound & Grounded)**",
            "INSUFFICIENT_CONTEXT": "🟡 **INSUFFICIENT CONTEXT (Withheld Pending Foundational Proofs)**",
            "INSUFFICIENT_EVIDENCE": "🟠 **INSUFFICIENT EVIDENCE**",
            "OUTSIDE_SCOPE": "⚪ **OUTSIDE STRUCTURAL SCOPE**",
            "UNRESOLVED": "⚠️ **UNRESOLVED**"
        }
        verdict_str = status_icons.get(verdict, f"**{verdict}**")

        lines = [
            f"<!-- intellectual-rigour:start framework=\"{self.id}\" source_hash=\"{source_hash}\" -->",
            self.section_heading,
            "",
            f"> **Epistemic Verdict**: {verdict_str}",
            f"> *Source Hash*: `{source_hash}` · *Framework*: René Descartes (First-Principles & Methodological Doubt)",
            "",
            f"{executive_summary}",
            ""
        ]

        if critiques:
            lines.append("#### Structural & Foundational Critiques")
            for idx, c in enumerate(critiques, 1):
                severity_badge = f"`{c.severity}`"
                blocking_badge = " · **BLOCKING**" if c.blocking else ""
                lines.append(f"##### {idx}. {c.target_claim_or_method} ({severity_badge}{blocking_badge})")
                lines.append(f"- **Problem**: {c.problem}")
                lines.append(f"- **Epistemic Impact**: {c.why_it_matters}")
                if c.evidence_or_counterexample:
                    lines.append(f"- **Dependency Failure / Cascade**: {c.evidence_or_counterexample}")
                if c.required_context:
                    lines.append(f"- **Required Context**: {c.required_context}")
                if c.recommendation:
                    lines.append(f"- **Remediation**: {c.recommendation}")
                lines.append(f"- *Provenance Rule*: `{c.provenance_rule}`")
                lines.append("")

        if primitive_foundations:
            lines.append("#### Isolated Atomic Primitives")
            for prim in primitive_foundations:
                lines.append(f"- 🧱 {prim}")
            lines.append("")

        if unresolved_questions:
            lines.append("#### Foundational First-Principles Questions")
            for q in unresolved_questions:
                lines.append(f"- ❓ {q}")
            lines.append("")

        if epistemic_notes:
            lines.append(f"> [!NOTE]\n> **Epistemic Grounding**: {epistemic_notes}")
            lines.append("")

        lines.append("<!-- intellectual-rigour:end -->")
        return "\n".join(lines)
