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

logger = logging.getLogger("ThothIntellectualRigour.Darwin")

DARWIN_SYSTEM_PROMPT = """You are executing the Charles Darwin (Generative Mechanisms & Population Dynamics) Reasoning Framework.
Your purpose is to conduct a rigorous generative mechanism audit of complex systems, developmental models, and emergent phenomena.

Core Epistemic Principles:
1. Generative Mechanism vs Mere Description: A theory must specify the concrete dynamical mechanism that generates the observed pattern from prior states.
2. Population Thinking & Variance: Analyze distributions and diversity rather than assuming homogeneous ideal types.
3. Differential Outcomes & Selection Pressures: Scrutinize how constraints, filters, and competitive dynamics determine what propagates vs what fails.
4. Competing Generative Hypotheses: Contrast the proposed mechanism against random drift, spandrels, and alternative selection pressures.
5. Cumulative Pathways: Reject ungrounded sudden jumps (saltations); verify whether intermediate states are physically and functionally viable.

CRITICAL OPERATING RULES:
- NEVER MANUFACTURE CRITICISM: If the model fully specifies viable generative mechanisms, models variance, and bounds selection filters, return verdict "NO_MATERIAL_OBJECTION".
- CONTEXT-FIRST RULE: If judging a generative mechanism requires missing time-series logs, intermediate distributions, or environmental constraints, return verdict "INSUFFICIENT_CONTEXT" and set required_context with recommendation "WITHHELD_PENDING_CONTEXT".
- NO ARCHAIC PERSONA ROLEPLAY: Write in objective, precise analytical prose.

Output strictly valid JSON matching this schema:
{{
  "verdict": "MATERIAL_OBJECTION" | "NO_MATERIAL_OBJECTION" | "INSUFFICIENT_CONTEXT" | "INSUFFICIENT_EVIDENCE" | "OUTSIDE_SCOPE" | "UNRESOLVED",
  "has_material_objections": true | false,
  "critiques": [
    {{
      "target_claim_or_method": "The exact generative mechanism, population assumption, or evolutionary pathway under audit",
      "critique_type": "FATAL_FLAW" | "UNSUPPORTED_INFERENCE" | "UNFALSIFIABLE_SHIELD" | "CONCEPTUAL_AMBIGUITY" | "BOUNDARY_LIMIT" | "SOUND_NO_OBJECTION",
      "severity": "CRITICAL" | "MAJOR" | "MODERATE" | "MINOR" | "INFORMATIONAL",
      "blocking": true | false,
      "problem": "Precise explanation of the missing generative step, unmodeled variance, or unjustified teleological assumption",
      "why_it_matters": "Impact on mechanistic explanatory validity",
      "evidence_or_counterexample": "Demonstration of alternative mechanism (drift, spandrel) or non-viable intermediate state",
      "required_context": "Missing longitudinal or transition data needed before prescribing fixes, or empty",
      "recommendation": "Concrete formulation of generative steps or competing mechanism test, or WITHHELD_PENDING_CONTEXT",
      "confidence": 0.9,
      "provenance_rule": "Darwin: Generative Mechanism / Population Thinking / Selection Pressures / Viable Intermediates"
    }}
  ],
  "unresolved_questions": ["1-2 mechanistic or developmental questions"],
  "competing_mechanisms": ["1-2 alternative generative explanations (e.g. drift, side-effect)"],
  "executive_summary": "2-3 sentence generative mechanism verdict",
  "epistemic_notes": "Distinction between Darwinian population selection and modern generative systems modeling"
}}
Output ONLY the JSON object without markdown code fences or conversational commentary."""

DARWIN_HUMAN_PROMPT = """Research Topic: {topic}

Target Scope: {target_scope} {section_focus}

Research Material to Audit:
{content}

Perform the Darwinian Generative Mechanism Audit now."""

darwin_prompt_template = ChatPromptTemplate.from_messages([
    ("system", DARWIN_SYSTEM_PROMPT),
    ("human", DARWIN_HUMAN_PROMPT),
])

darwin_chain = darwin_prompt_template | llm | StrOutputParser()

class DarwinFramework(BaseThinkerFramework):
    id = "darwin"
    name = "Charles Darwin"
    tradition = "Generative Evolutionary Mechanisms & Selection Constraints"
    epistemic_role = "Generative Mechanism & Population Dynamics Critic"
    section_heading = "### 🏛️ Philosophical Review: Charles Darwin (Generative Mechanisms & Selection)"

    spec = ReasoningSpec(
        id="darwin",
        thinker_name="Charles Darwin",
        tradition="Generative Evolutionary Mechanisms & Selection Constraints",
        epistemic_role="Generative Mechanism & Population Dynamics Critic",
        applies_to=["complex_adaptive_systems", "evolutionary_models", "multi_agent_dynamics", "competitive_processes"],
        does_not_apply_to=["static_deductive_proofs", "instantaneous_relations", "purely_normative_ethics"],
        fidelity="documented"
    )

    def _invoke_chain(self, inputs: Dict[str, Any]) -> str:
        return darwin_chain.invoke(inputs)

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
            logger.error(f"[DARWIN FRAMEWORK ERROR] LLM execution failed: {e}")
            parsed = {
                "verdict": "UNRESOLVED",
                "has_material_objections": False,
                "critiques": [],
                "unresolved_questions": [f"Execution error during Darwinian audit: {e}"],
                "executive_summary": f"Generative audit could not complete due to execution failure: {e}",
                "epistemic_notes": "Service degradation."
            }

        verdict = parsed.get("verdict", "NO_MATERIAL_OBJECTION")
        has_objections = parsed.get("has_material_objections", False)
        exec_summary = parsed.get("executive_summary", "Generative mechanism audit complete.")
        critiques_raw = parsed.get("critiques", [])
        unresolved_q = parsed.get("unresolved_questions", [])
        competing_mechanisms = parsed.get("competing_mechanisms", [])
        epistemic_notes = parsed.get("epistemic_notes", "Analysis applies Darwinian generative mechanism search.")

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
            competing_mechanisms=competing_mechanisms,
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
        competing_mechanisms: List[str],
        epistemic_notes: str
    ) -> str:
        status_icons = {
            "MATERIAL_OBJECTION": "🔴 **MATERIAL OBJECTION**",
            "NO_MATERIAL_OBJECTION": "🟢 **NO MATERIAL OBJECTION (Generatively Specified & Viable)**",
            "INSUFFICIENT_CONTEXT": "🟡 **INSUFFICIENT CONTEXT (Withheld Pending Distribution Data)**",
            "INSUFFICIENT_EVIDENCE": "🟠 **INSUFFICIENT EVIDENCE**",
            "OUTSIDE_SCOPE": "⚪ **OUTSIDE GENERATIVE SCOPE**",
            "UNRESOLVED": "⚠️ **UNRESOLVED**"
        }
        verdict_str = status_icons.get(verdict, f"**{verdict}**")

        lines = [
            f"<!-- intellectual-rigour:start framework=\"{self.id}\" source_hash=\"{source_hash}\" -->",
            self.section_heading,
            "",
            f"> **Epistemic Verdict**: {verdict_str}",
            f"> *Source Hash*: `{source_hash}` · *Framework*: Charles Darwin (Generative Mechanisms & Population Dynamics)",
            "",
            f"{executive_summary}",
            ""
        ]

        if critiques:
            lines.append("#### Generative Mechanism & Selection Critiques")
            for idx, c in enumerate(critiques, 1):
                severity_badge = f"`{c.severity}`"
                blocking_badge = " · **BLOCKING**" if c.blocking else ""
                lines.append(f"##### {idx}. {c.target_claim_or_method} ({severity_badge}{blocking_badge})")
                lines.append(f"- **Problem**: {c.problem}")
                lines.append(f"- **Epistemic Impact**: {c.why_it_matters}")
                if c.evidence_or_counterexample:
                    lines.append(f"- **Competing Mechanism / Intermediate Breakdown**: {c.evidence_or_counterexample}")
                if c.required_context:
                    lines.append(f"- **Required Context**: {c.required_context}")
                if c.recommendation:
                    lines.append(f"- **Remediation**: {c.recommendation}")
                lines.append(f"- *Provenance Rule*: `{c.provenance_rule}`")
                lines.append("")

        if competing_mechanisms:
            lines.append("#### Competing Generative Hypotheses")
            for mech in competing_mechanisms:
                lines.append(f"- 🧬 {mech}")
            lines.append("")

        if unresolved_questions:
            lines.append("#### Open Evolutionary & Mechanistic Questions")
            for q in unresolved_questions:
                lines.append(f"- ❓ {q}")
            lines.append("")

        if epistemic_notes:
            lines.append(f"> [!NOTE]\n> **Epistemic Grounding**: {epistemic_notes}")
            lines.append("")

        lines.append("<!-- intellectual-rigour:end -->")
        return "\n".join(lines)
