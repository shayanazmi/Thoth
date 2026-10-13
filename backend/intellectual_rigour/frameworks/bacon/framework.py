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

logger = logging.getLogger("ThothIntellectualRigour.Bacon")

BACON_SYSTEM_PROMPT = """You are executing the Francis Bacon (Eliminative Induction & Empirical Rigour) Reasoning Framework.
Your purpose is to conduct a rigorous, objective empirical audit of research claims, datasets, ablations, and generalizations.

Core Epistemic Principles:
1. Eliminative Induction: True empirical proof requires systematic exclusion of alternative explanations and confounding factors, not just positive examples.
2. Tables of Presence & Absence: Scrutinize whether negative cases, failure modes, and boundary instances were investigated alongside positive results.
3. Four Idols Audit:
   - Tribe: Confirmation bias, premature closure, finding false patterns in noise.
   - Cave: Domain bias, tool-induced blindness, researcher specialty blinkers.
   - Marketplace: Inflated terminology, buzzwords, ambiguous empirical metrics.
   - Theatre: Dogmatic adherence to prevailing benchmark paradigms or fashionable authorities.
4. Experimentum Crucis (Crucial Discriminating Test): Identify definitive comparative experiments where competing explanations make incompatible predictions.
5. Gradual Induction Ladder: Flag any leap from narrow experimental observations directly to sweeping universal claims without intermediate steps.

CRITICAL OPERATING RULES:
- NEVER MANUFACTURE CRITICISM: If the research provides robust negative controls, thorough ablations, and disciplined empirical claims, return verdict "NO_MATERIAL_OBJECTION".
- CONTEXT-FIRST RULE: If judging an inductive claim requires missing raw control tables or negative dataset distributions, return verdict "INSUFFICIENT_CONTEXT" and set required_context with recommendation "WITHHELD_PENDING_CONTEXT".
- NO ARCHAIC PERSONA ROLEPLAY: Write in objective, precise analytical prose.

Output strictly valid JSON matching this schema:
{{
  "verdict": "MATERIAL_OBJECTION" | "NO_MATERIAL_OBJECTION" | "INSUFFICIENT_CONTEXT" | "INSUFFICIENT_EVIDENCE" | "OUTSIDE_SCOPE" | "UNRESOLVED",
  "has_material_objections": true | false,
  "critiques": [
    {{
      "target_claim_or_method": "The exact empirical claim, dataset, ablation, or generalization under audit",
      "critique_type": "FATAL_FLAW" | "UNSUPPORTED_INFERENCE" | "UNFALSIFIABLE_SHIELD" | "CONCEPTUAL_AMBIGUITY" | "BOUNDARY_LIMIT" | "SOUND_NO_OBJECTION",
      "severity": "CRITICAL" | "MAJOR" | "MODERATE" | "MINOR" | "INFORMATIONAL",
      "blocking": true | false,
      "problem": "Precise explanation of the selective observation, unexcluded confounder, idol bias, or inductive overreach",
      "why_it_matters": "Impact on empirical validity and generalizability",
      "evidence_or_counterexample": "Specific negative instance, confounder, or idol manifestation",
      "required_context": "Missing control dataset or ablation data needed before prescribing fixes, or empty",
      "recommendation": "Concrete discriminating test or control experiment, or WITHHELD_PENDING_CONTEXT",
      "confidence": 0.9,
      "provenance_rule": "Bacon: Eliminative Induction / Tables of Absence / Four Idols / Crucial Experiment"
    }}
  ],
  "unresolved_questions": ["1-2 empirical or control questions"],
  "discriminating_tests": ["1-2 crucial comparative experiments (Experimentum Crucis)"],
  "executive_summary": "2-3 sentence empirical and inductive verdict",
  "epistemic_notes": "Distinction between Baconian eliminative tables and modern statistical ablation testing"
}}
Output ONLY the JSON object without markdown code fences or conversational commentary."""

BACON_HUMAN_PROMPT = """Research Topic: {topic}

Target Scope: {target_scope} {section_focus}

Research Material to Audit:
{content}

Perform the Baconian Inductive & Empirical Audit now."""

bacon_prompt_template = ChatPromptTemplate.from_messages([
    ("system", BACON_SYSTEM_PROMPT),
    ("human", BACON_HUMAN_PROMPT),
])

bacon_chain = bacon_prompt_template | llm | StrOutputParser()

class BaconFramework(BaseThinkerFramework):
    id = "bacon"
    name = "Francis Bacon"
    tradition = "Systematic Eliminative Induction & Empiricism"
    epistemic_role = "Empirical Evidence & Eliminative Induction Critic"
    section_heading = "### 🏛️ Philosophical Review: Francis Bacon (Eliminative Induction & Idols)"

    spec = ReasoningSpec(
        id="bacon",
        thinker_name="Francis Bacon",
        tradition="Systematic Eliminative Induction & Empiricism",
        epistemic_role="Empirical Evidence & Eliminative Induction Critic",
        applies_to=["empirical_studies", "observational_data", "benchmarks", "ablation_studies", "inductive_generalizations"],
        does_not_apply_to=["pure_mathematics", "formal_syntax_definitions", "non_empirical_deductive_systems"],
        fidelity="documented"
    )

    def _invoke_chain(self, inputs: Dict[str, Any]) -> str:
        return bacon_chain.invoke(inputs)

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
            logger.error(f"[BACON FRAMEWORK ERROR] LLM execution failed: {e}")
            parsed = {
                "verdict": "UNRESOLVED",
                "has_material_objections": False,
                "critiques": [],
                "unresolved_questions": [f"Execution error during Baconian audit: {e}"],
                "executive_summary": f"Inductive audit could not complete due to execution failure: {e}",
                "epistemic_notes": "Service degradation."
            }

        verdict = parsed.get("verdict", "NO_MATERIAL_OBJECTION")
        has_objections = parsed.get("has_material_objections", False)
        exec_summary = parsed.get("executive_summary", "Empirical inductive audit complete.")
        critiques_raw = parsed.get("critiques", [])
        unresolved_q = parsed.get("unresolved_questions", [])
        discriminating_tests = parsed.get("discriminating_tests", [])
        epistemic_notes = parsed.get("epistemic_notes", "Analysis applies Baconian eliminative induction.")

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
            discriminating_tests=discriminating_tests,
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
        discriminating_tests: List[str],
        epistemic_notes: str
    ) -> str:
        status_icons = {
            "MATERIAL_OBJECTION": "🔴 **MATERIAL OBJECTION**",
            "NO_MATERIAL_OBJECTION": "🟢 **NO MATERIAL OBJECTION (Empirically Corroborated & Eliminated)**",
            "INSUFFICIENT_CONTEXT": "🟡 **INSUFFICIENT CONTEXT (Withheld Pending Negative Controls)**",
            "INSUFFICIENT_EVIDENCE": "🟠 **INSUFFICIENT EVIDENCE**",
            "OUTSIDE_SCOPE": "⚪ **OUTSIDE EMPIRICAL SCOPE**",
            "UNRESOLVED": "⚠️ **UNRESOLVED**"
        }
        verdict_str = status_icons.get(verdict, f"**{verdict}**")

        lines = [
            f"<!-- intellectual-rigour:start framework=\"{self.id}\" source_hash=\"{source_hash}\" -->",
            self.section_heading,
            "",
            f"> **Epistemic Verdict**: {verdict_str}",
            f"> *Source Hash*: `{source_hash}` · *Framework*: Francis Bacon (Eliminative Induction & Four Idols)",
            "",
            f"{executive_summary}",
            ""
        ]

        if critiques:
            lines.append("#### Inductive & Bias Critiques")
            for idx, c in enumerate(critiques, 1):
                severity_badge = f"`{c.severity}`"
                blocking_badge = " · **BLOCKING**" if c.blocking else ""
                lines.append(f"##### {idx}. {c.target_claim_or_method} ({severity_badge}{blocking_badge})")
                lines.append(f"- **Problem**: {c.problem}")
                lines.append(f"- **Epistemic Impact**: {c.why_it_matters}")
                if c.evidence_or_counterexample:
                    lines.append(f"- **Negative Instance / Confounder / Idol**: {c.evidence_or_counterexample}")
                if c.required_context:
                    lines.append(f"- **Required Context**: {c.required_context}")
                if c.recommendation:
                    lines.append(f"- **Remediation**: {c.recommendation}")
                lines.append(f"- *Provenance Rule*: `{c.provenance_rule}`")
                lines.append("")

        if discriminating_tests:
            lines.append("#### Crucial Discriminating Experiments (*Experimentum Crucis*)")
            for test in discriminating_tests:
                lines.append(f"- 🔬 {test}")
            lines.append("")

        if unresolved_questions:
            lines.append("#### Open Empirical Questions")
            for q in unresolved_questions:
                lines.append(f"- ❓ {q}")
            lines.append("")

        if epistemic_notes:
            lines.append(f"> [!NOTE]\n> **Epistemic Grounding**: {epistemic_notes}")
            lines.append("")

        lines.append("<!-- intellectual-rigour:end -->")
        return "\n".join(lines)
