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

logger = logging.getLogger("ThothIntellectualRigour.Hume")

HUME_SYSTEM_PROMPT = """You are executing the David Hume (Radical Empiricism & Causal Skepticism) Reasoning Framework.
Your purpose is to conduct a rigorous, skeptical audit of causal assertions, inferential leaps, and inductive overreach.

Core Epistemic Principles:
1. Demarcate Observation from Inference: Classify claims by Epistemic Distance (0=Direct Observation, 1=Reported Data, 2=Correlation, 3=Inferred Mechanism, 4=Necessary Law).
2. Constant Conjunction vs Necessity: Distinguish observed correlation/succession from demonstrated causal power.
3. Attack Causal Attributions: For every asserted A -> B link, systematically test alternatives (Reverse causality B->A, Common confounder C->(A,B), Selection bias, Coincidence).
4. Problem of Induction: Scrutinize whether projecting empirical regularities out-of-distribution is ungrounded.
5. Calibrate Claims: Demand that certainty be downgraded to probability, and causal claims be bounded to tested conditions.

CRITICAL OPERATING RULES:
- NEVER MANUFACTURE CRITICISM: If causal claims are backed by rigorous interventional or randomized controls with calibrated probabilistic claims, return verdict "NO_MATERIAL_OBJECTION".
- CONTEXT-FIRST RULE: If judging a causal assertion requires missing confounder matrices or covariate data, return verdict "INSUFFICIENT_CONTEXT" and set required_context with recommendation "WITHHELD_PENDING_CONTEXT".
- NO ARCHAIC PERSONA ROLEPLAY: Write in objective, precise analytical prose.

Output strictly valid JSON matching this schema:
{{
  "verdict": "MATERIAL_OBJECTION" | "NO_MATERIAL_OBJECTION" | "INSUFFICIENT_CONTEXT" | "INSUFFICIENT_EVIDENCE" | "OUTSIDE_SCOPE" | "UNRESOLVED",
  "has_material_objections": true | false,
  "critiques": [
    {{
      "target_claim_or_method": "The exact causal claim or inductive projection under audit",
      "critique_type": "FATAL_FLAW" | "UNSUPPORTED_INFERENCE" | "UNFALSIFIABLE_SHIELD" | "CONCEPTUAL_AMBIGUITY" | "BOUNDARY_LIMIT" | "SOUND_NO_OBJECTION",
      "severity": "CRITICAL" | "MAJOR" | "MODERATE" | "MINOR" | "INFORMATIONAL",
      "blocking": true | false,
      "problem": "Precise explanation of the inferential jump, unaddressed confounder, or spurious correlation",
      "why_it_matters": "Impact on causal validity and empirical reliability",
      "evidence_or_counterexample": "Specific alternative causal explanation (reverse, confounder, selection bias)",
      "required_context": "Missing interventional or observational data needed before prescribing fixes, or empty",
      "recommendation": "Concrete calibration to probabilistic bounds or interventional experiment, or WITHHELD_PENDING_CONTEXT",
      "confidence": 0.9,
      "provenance_rule": "Hume: Constant Conjunction / Inferential Jump / Confounder Attack / Epistemic Calibration"
    }}
  ],
  "unresolved_questions": ["1-2 critical causal or inductive questions"],
  "alternative_causal_hypotheses": ["1-2 concrete alternative causal mechanisms"],
  "executive_summary": "2-3 sentence causal skepticism and calibration verdict",
  "epistemic_notes": "Distinction between Humean skepticism and modern DAG/do-calculus causal inference"
}}
Output ONLY the JSON object without markdown code fences or conversational commentary."""

HUME_HUMAN_PROMPT = """Research Topic: {topic}

Target Scope: {target_scope} {section_focus}

Research Material to Audit:
{content}

Perform the Humean Causal & Inferential Audit now."""

hume_prompt_template = ChatPromptTemplate.from_messages([
    ("system", HUME_SYSTEM_PROMPT),
    ("human", HUME_HUMAN_PROMPT),
])

hume_chain = hume_prompt_template | llm | StrOutputParser()

class HumeFramework(BaseThinkerFramework):
    id = "hume"
    name = "David Hume"
    tradition = "Radical Empiricism & Causal Skepticism"
    epistemic_role = "Causal Inference & Epistemic Calibration Critic"
    section_heading = "### 🏛️ Philosophical Review: David Hume (Causal Skepticism & Calibration)"

    spec = ReasoningSpec(
        id="hume",
        thinker_name="David Hume",
        tradition="Radical Empiricism & Causal Skepticism",
        epistemic_role="Causal Inference & Epistemic Calibration Critic",
        applies_to=["causal_claims", "statistical_associations", "inductive_projections", "observational_studies"],
        does_not_apply_to=["pure_deductive_mathematics", "formal_syntax_proofs", "non_empirical_definitions"],
        fidelity="documented"
    )

    def _invoke_chain(self, inputs: Dict[str, Any]) -> str:
        return hume_chain.invoke(inputs)

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
            logger.error(f"[HUME FRAMEWORK ERROR] LLM execution failed: {e}")
            parsed = {
                "verdict": "UNRESOLVED",
                "has_material_objections": False,
                "critiques": [],
                "unresolved_questions": [f"Execution error during Humean audit: {e}"],
                "executive_summary": f"Causal audit could not complete due to execution failure: {e}",
                "epistemic_notes": "Service degradation."
            }

        verdict = parsed.get("verdict", "NO_MATERIAL_OBJECTION")
        has_objections = parsed.get("has_material_objections", False)
        exec_summary = parsed.get("executive_summary", "Causal and inferential audit complete.")
        critiques_raw = parsed.get("critiques", [])
        unresolved_q = parsed.get("unresolved_questions", [])
        alt_hypotheses = parsed.get("alternative_causal_hypotheses", [])
        epistemic_notes = parsed.get("epistemic_notes", "Analysis applies Humean skepticism and epistemic calibration.")

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
            alternative_hypotheses=alt_hypotheses,
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
        alternative_hypotheses: List[str],
        epistemic_notes: str
    ) -> str:
        status_icons = {
            "MATERIAL_OBJECTION": "🔴 **MATERIAL OBJECTION**",
            "NO_MATERIAL_OBJECTION": "🟢 **NO MATERIAL OBJECTION (Causally Controlled & Calibrated)**",
            "INSUFFICIENT_CONTEXT": "🟡 **INSUFFICIENT CONTEXT (Withheld Pending Interventional Data)**",
            "INSUFFICIENT_EVIDENCE": "🟠 **INSUFFICIENT EVIDENCE**",
            "OUTSIDE_SCOPE": "⚪ **OUTSIDE CAUSAL SCOPE**",
            "UNRESOLVED": "⚠️ **UNRESOLVED**"
        }
        verdict_str = status_icons.get(verdict, f"**{verdict}**")

        lines = [
            f"<!-- intellectual-rigour:start framework=\"{self.id}\" source_hash=\"{source_hash}\" -->",
            self.section_heading,
            "",
            f"> **Epistemic Verdict**: {verdict_str}",
            f"> *Source Hash*: `{source_hash}` · *Framework*: David Hume (Causal Skepticism & Inferential Jumps)",
            "",
            f"{executive_summary}",
            ""
        ]

        if critiques:
            lines.append("#### Causal Inference & Skeptical Critiques")
            for idx, c in enumerate(critiques, 1):
                severity_badge = f"`{c.severity}`"
                blocking_badge = " · **BLOCKING**" if c.blocking else ""
                lines.append(f"##### {idx}. {c.target_claim_or_method} ({severity_badge}{blocking_badge})")
                lines.append(f"- **Problem**: {c.problem}")
                lines.append(f"- **Epistemic Impact**: {c.why_it_matters}")
                if c.evidence_or_counterexample:
                    lines.append(f"- **Confounder / Alternative Hypothesis**: {c.evidence_or_counterexample}")
                if c.required_context:
                    lines.append(f"- **Required Context**: {c.required_context}")
                if c.recommendation:
                    lines.append(f"- **Calibration / Remediation**: {c.recommendation}")
                lines.append(f"- *Provenance Rule*: `{c.provenance_rule}`")
                lines.append("")

        if alternative_hypotheses:
            lines.append("#### Competing Causal Explanations")
            for alt in alternative_hypotheses:
                lines.append(f"- 🔀 {alt}")
            lines.append("")

        if unresolved_questions:
            lines.append("#### Open Causal Questions")
            for q in unresolved_questions:
                lines.append(f"- ❓ {q}")
            lines.append("")

        if epistemic_notes:
            lines.append(f"> [!NOTE]\n> **Epistemic Grounding**: {epistemic_notes}")
            lines.append("")

        lines.append("<!-- intellectual-rigour:end -->")
        return "\n".join(lines)
