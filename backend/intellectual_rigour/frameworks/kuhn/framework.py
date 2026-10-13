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

logger = logging.getLogger("ThothIntellectualRigour.Kuhn")

KUHN_SYSTEM_PROMPT = """You are executing the Thomas Kuhn (Paradigm Shifts & Disciplinary Matrices) Reasoning Framework.
Your purpose is to conduct a rigorous analysis of research novelty, paradigm dependence, and anomaly resolution.

Core Epistemic Principles:
1. Disciplinary Matrix & Normal Science: Identify prevailing baseline assumptions, standard benchmarks, and whether work is incremental puzzle-solving.
2. Anomaly Detection: Surface persistent failures, unexplained exceptions, or performance walls that current consensus approaches dismiss.
3. Classify Contribution: Accurately categorize into Normal Puzzle-Solving, Anomaly Resolution, Framework Modification, or True Paradigm Shift.
4. Paradigm Dependence: Test whether findings only make sense within current assumptions or hold across alternative conceptual frameworks.
5. Unmask Inflated Breakthrough Claims: Distinguish genuinely transformative conceptual changes from incremental optimizations marketed as revolutions.

CRITICAL OPERATING RULES:
- NEVER MANUFACTURE CRITICISM: If research honestly frames its scope and successfully solves recognized puzzles within its paradigm, return verdict "NO_MATERIAL_OBJECTION".
- CONTEXT-FIRST RULE: If judging paradigm novelty requires missing historical lineages or comparative field standards, return verdict "INSUFFICIENT_CONTEXT" and set required_context with recommendation "WITHHELD_PENDING_CONTEXT".
- NO ARCHAIC PERSONA ROLEPLAY: Write in objective, precise analytical prose.

Output strictly valid JSON matching this schema:
{{
  "verdict": "MATERIAL_OBJECTION" | "NO_MATERIAL_OBJECTION" | "INSUFFICIENT_CONTEXT" | "INSUFFICIENT_EVIDENCE" | "OUTSIDE_SCOPE" | "UNRESOLVED",
  "has_material_objections": true | false,
  "critiques": [
    {{
      "target_claim_or_method": "The exact novelty claim, paradigm assumption, or anomaly under audit",
      "critique_type": "FATAL_FLAW" | "UNSUPPORTED_INFERENCE" | "UNFALSIFIABLE_SHIELD" | "CONCEPTUAL_AMBIGUITY" | "BOUNDARY_LIMIT" | "SOUND_NO_OBJECTION",
      "severity": "CRITICAL" | "MAJOR" | "MODERATE" | "MINOR" | "INFORMATIONAL",
      "blocking": true | false,
      "problem": "Precise explanation of the false novelty claim, ignored anomaly, or excessive paradigm dependence",
      "why_it_matters": "Impact on true scientific contribution and disciplinary progress",
      "evidence_or_counterexample": "Specific anomaly or demonstrated lack of conceptual displacement",
      "required_context": "Missing field baseline context needed before prescribing fixes, or empty",
      "recommendation": "Concrete re-framing of contribution or competing paradigm comparison, or WITHHELD_PENDING_CONTEXT",
      "confidence": 0.9,
      "provenance_rule": "Kuhn: Normal Science vs Paradigm Shift / Anomaly Suppression / Paradigm Dependence"
    }}
  ],
  "unresolved_questions": ["1-2 paradigm-level questions"],
  "paradigm_anomalies": ["1-2 persistent anomalies within the domain"],
  "executive_summary": "2-3 sentence paradigm and novelty verdict",
  "epistemic_notes": "Distinction between Kuhnian paradigm dynamics and modern incremental benchmark competition"
}}
Output ONLY the JSON object without markdown code fences or conversational commentary."""

KUHN_HUMAN_PROMPT = """Research Topic: {topic}

Target Scope: {target_scope} {section_focus}

Research Material to Audit:
{content}

Perform the Kuhnian Paradigm & Novelty Audit now."""

kuhn_prompt_template = ChatPromptTemplate.from_messages([
    ("system", KUHN_SYSTEM_PROMPT),
    ("human", KUHN_HUMAN_PROMPT),
])

kuhn_chain = kuhn_prompt_template | llm | StrOutputParser()

class KuhnFramework(BaseThinkerFramework):
    id = "kuhn"
    name = "Thomas Kuhn"
    tradition = "Historiography of Science & Paradigm Analysis"
    epistemic_role = "Paradigm Analysis & Contribution Novelty Critic"
    section_heading = "### 🏛️ Philosophical Review: Thomas Kuhn (Paradigm Shifts & Novelty)"

    spec = ReasoningSpec(
        id="kuhn",
        thinker_name="Thomas Kuhn",
        tradition="Historiography of Science & Paradigm Analysis",
        epistemic_role="Paradigm Analysis & Contribution Novelty Critic",
        applies_to=["novelty_claims", "architectural_shifts", "methodological_breakthroughs", "disciplinary_assumptions", "anomalies"],
        does_not_apply_to=["routine_hyperparameter_tuning", "ordinary_bugfixes", "narrow_data_cleaning"],
        fidelity="documented"
    )

    def _invoke_chain(self, inputs: Dict[str, Any]) -> str:
        return kuhn_chain.invoke(inputs)

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
            logger.error(f"[KUHN FRAMEWORK ERROR] LLM execution failed: {e}")
            parsed = {
                "verdict": "UNRESOLVED",
                "has_material_objections": False,
                "critiques": [],
                "unresolved_questions": [f"Execution error during Kuhnian audit: {e}"],
                "executive_summary": f"Paradigm audit could not complete due to execution failure: {e}",
                "epistemic_notes": "Service degradation."
            }

        verdict = parsed.get("verdict", "NO_MATERIAL_OBJECTION")
        has_objections = parsed.get("has_material_objections", False)
        exec_summary = parsed.get("executive_summary", "Paradigm and contribution audit complete.")
        critiques_raw = parsed.get("critiques", [])
        unresolved_q = parsed.get("unresolved_questions", [])
        anomalies = parsed.get("paradigm_anomalies", [])
        epistemic_notes = parsed.get("epistemic_notes", "Analysis applies Kuhnian paradigm dynamics.")

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
            anomalies=anomalies,
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
        anomalies: List[str],
        epistemic_notes: str
    ) -> str:
        status_icons = {
            "MATERIAL_OBJECTION": "🔴 **MATERIAL OBJECTION**",
            "NO_MATERIAL_OBJECTION": "🟢 **NO MATERIAL OBJECTION (Accurately Framed & Solves Paradigm Puzzles)**",
            "INSUFFICIENT_CONTEXT": "🟡 **INSUFFICIENT CONTEXT (Withheld Pending Baseline Standards)**",
            "INSUFFICIENT_EVIDENCE": "🟠 **INSUFFICIENT EVIDENCE**",
            "OUTSIDE_SCOPE": "⚪ **OUTSIDE PARADIGM SCOPE**",
            "UNRESOLVED": "⚠️ **UNRESOLVED**"
        }
        verdict_str = status_icons.get(verdict, f"**{verdict}**")

        lines = [
            f"<!-- intellectual-rigour:start framework=\"{self.id}\" source_hash=\"{source_hash}\" -->",
            self.section_heading,
            "",
            f"> **Epistemic Verdict**: {verdict_str}",
            f"> *Source Hash*: `{source_hash}` · *Framework*: Thomas Kuhn (Paradigm Shifts & Disciplinary Matrices)",
            "",
            f"{executive_summary}",
            ""
        ]

        if critiques:
            lines.append("#### Paradigm & Novelty Critiques")
            for idx, c in enumerate(critiques, 1):
                severity_badge = f"`{c.severity}`"
                blocking_badge = " · **BLOCKING**" if c.blocking else ""
                lines.append(f"##### {idx}. {c.target_claim_or_method} ({severity_badge}{blocking_badge})")
                lines.append(f"- **Problem**: {c.problem}")
                lines.append(f"- **Epistemic Impact**: {c.why_it_matters}")
                if c.evidence_or_counterexample:
                    lines.append(f"- **Anomaly / Paradigm Conflict**: {c.evidence_or_counterexample}")
                if c.required_context:
                    lines.append(f"- **Required Context**: {c.required_context}")
                if c.recommendation:
                    lines.append(f"- **Remediation**: {c.recommendation}")
                lines.append(f"- *Provenance Rule*: `{c.provenance_rule}`")
                lines.append("")

        if anomalies:
            lines.append("#### Highlighted Domain Anomalies")
            for a in anomalies:
                lines.append(f"- 🌀 {a}")
            lines.append("")

        if unresolved_questions:
            lines.append("#### Open Paradigm Questions")
            for q in unresolved_questions:
                lines.append(f"- ❓ {q}")
            lines.append("")

        if epistemic_notes:
            lines.append(f"> [!NOTE]\n> **Epistemic Grounding**: {epistemic_notes}")
            lines.append("")

        lines.append("<!-- intellectual-rigour:end -->")
        return "\n".join(lines)
