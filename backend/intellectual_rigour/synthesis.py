from typing import List, Dict, Any, Optional
import logging
from pydantic import BaseModel, Field

from backend.agents import llm, safe_extract_json, strip_chain_of_thought
from backend.intellectual_rigour.models import (
    ReviewRequest,
    ReviewArtifact,
    ThinkerOutput,
    CritiqueFinding,
)
from backend.intellectual_rigour.registry import get_framework, list_registered_thinkers
from backend.intellectual_rigour.attack_surface import detect_attack_surfaces
from backend.intellectual_rigour.frameworks.base import strip_existing_intellectual_rigour_blocks
from backend.reports.patch import patch_report_section

logger = logging.getLogger("ThothIntellectualRigour.Synthesis")

class SynthesisResult(BaseModel):
    participating_thinkers: List[str] = Field(default_factory=list)
    agreements: List[str] = Field(default_factory=list, description="Shared strengths or corroborated elements across thinkers.")
    shared_objections: List[str] = Field(default_factory=list, description="Methodological flaws identified by multiple independent frameworks.")
    disagreements_and_conflicts: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Explicit tensions between different traditions (e.g. deductive necessity vs empirical satisficing)."
    )
    blind_spots_surfaced: List[str] = Field(default_factory=list, description="Unexamined assumptions revealed by framework contrasts.")
    contribution_dimensions: Dict[str, str] = Field(
        default_factory=dict,
        description="Assessed dimensions (e.g. falsifiability, causal_credibility, parsimony, novelty)."
    )
    executive_verdict: str = Field(description="Comprehensive multi-perspective epistemic assessment.")

SYNTHESIS_SYSTEM_PROMPT = """You are the Lead Epistemic Synthesizer for the Thoth Intellectual Rigour Subsystem.
You have received independent, structured methodological critique outputs from multiple distinct historical reasoning frameworks evaluating the same research work.

Your task is to conduct a multi-framework synthesis and contribution assessment.

CRITICAL OPERATING PRINCIPLES:
1. PRESERVE INTELLECTUAL DISAGREEMENT: Do NOT collapse distinct philosophical stances into an averaged consensus or single numerical score.
2. EXPLAIN THE ROOT OF CONFLICTS: If Aristotle finds conceptual ambiguity while Simon finds heuristic satisficing adequate, or if Popper demands fatal refutation while Box seeks bounded utility, explain WHY their foundational axioms diverge.
3. IDENTIFY SHARED OBJECTIONS: Surface problems where independent methodologies converge on the exact same empirical or logical vulnerability.
4. SURFACE BLIND SPOTS: Highlight unexamined assumptions that only become visible when contrasting different frameworks.
5. RIGOROUS CONTRIBUTION ASSESSMENT: Assess the work across relevant dimensions: conceptual clarity, logical validity, evidence sufficiency, causal credibility, falsifiability, model adequacy, computational validity, paradigm novelty, and satisficing efficiency.

Output strictly valid JSON:
{{
  "agreements": ["1-2 points of cross-framework agreement"],
  "shared_objections": ["1-2 critical flaws corroborated by multiple thinkers"],
  "disagreements_and_conflicts": [
    {{
      "conflict_summary": "Tension between strict falsifiability and empirical model utility",
      "frameworks_involved": "Popper vs Box",
      "underlying_cause": "Popper demands severe refutation tests while Box accepts approximation errors within bounded utility domains.",
      "material_impact": "Conclusions hold for engineering deployment but remain uncorroborated as universal physical laws."
    }}
  ],
  "blind_spots_surfaced": ["1-2 hidden assumptions revealed by framework contrasts"],
  "contribution_dimensions": {{
    "conceptual_clarity": "High / Moderate / Low - brief evaluation",
    "causal_credibility": "High / Moderate / Low - brief evaluation",
    "falsifiability": "High / Moderate / Low - brief evaluation",
    "computational_validity": "High / Moderate / Low - brief evaluation"
  }},
  "executive_verdict": "3-4 sentence comprehensive synthesis evaluating overall research contribution and reliability."
}}"""

SYNTHESIS_HUMAN_PROMPT = """Research Topic: {topic}

Individual Thinker Review Outputs:
{thinker_reviews_summary}

Conduct the Multi-Framework Cross-Thinker Synthesis now."""

def run_multi_framework_synthesis(
    report_text: str,
    topic: str = "",
    requested_framework_ids: Optional[List[str]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> ReviewArtifact:
    if not report_text or not report_text.strip():
        empty_hash = "000000000000"
        return ReviewArtifact(
            framework_id="rigour_synthesis",
            target_section_title="### 🏛️ Intellectual Rigour: Multi-Framework Synthesis",
            operation="append_section",
            formatted_markdown="<!-- intellectual-rigour:start framework=\"rigour_synthesis\" -->\n### 🏛️ Intellectual Rigour: Multi-Framework Synthesis\n> No substantive content provided.\n<!-- intellectual-rigour:end -->",
            source_hash=empty_hash,
            metadata={"verdict": "OUTSIDE_SCOPE"}
        )

    if not requested_framework_ids:
        profile = detect_attack_surfaces(report_text, topic=topic)
        framework_ids = profile.recommended_framework_ids[:4]
    else:
        framework_ids = requested_framework_ids

    individual_artifacts: List[ReviewArtifact] = []
    thinker_summaries = []

    from backend.intellectual_rigour.frameworks.base import strip_existing_intellectual_rigour_blocks
    import hashlib
    cleaned_source = strip_existing_intellectual_rigour_blocks(report_text)
    source_hash = hashlib.sha256(cleaned_source.encode("utf-8")).hexdigest()[:12]

    req = ReviewRequest(query=f"/rigour topic={topic}")

    for fid in framework_ids:
        fw = get_framework(fid)
        if not fw:
            continue
        try:
            art = fw.review(request=req, report_text=report_text, topic=topic, context=context)
            individual_artifacts.append(art)
            verdict = art.metadata.get("verdict", "COMPLETED")
            critique_count = art.metadata.get("critiques_count", 0)
            thinker_summaries.append(
                f"### {fw.name} ({fw.tradition}) - Verdict: {verdict} ({critique_count} findings)\n{art.formatted_markdown[:2000]}"
            )
        except Exception as e:
            logger.error(f"[SYNTHESIS FRAMEWORK ERROR] Framework {fid} failed: {e}")

    combined_reviews_text = "\n\n---\n\n".join(thinker_summaries)
    try:
        raw_synth = llm.invoke(
            f"{SYNTHESIS_SYSTEM_PROMPT}\n\nHuman: {SYNTHESIS_HUMAN_PROMPT.format(topic=topic or 'Research Investigation', thinker_reviews_summary=combined_reviews_text[:14000])}"
        )
        cleaned_synth = strip_chain_of_thought(getattr(raw_synth, "content", str(raw_synth)))
        parsed_synth = safe_extract_json(cleaned_synth, default={})
    except Exception as e:
        logger.error(f"[SYNTHESIS LLM ERROR] {e}")
        parsed_synth = {
            "agreements": ["Independent reviews completed."],
            "shared_objections": [],
            "disagreements_and_conflicts": [],
            "blind_spots_surfaced": [],
            "contribution_dimensions": {"status": "Review generated under fallback"},
            "executive_verdict": f"Multi-thinker reviews conducted across {len(individual_artifacts)} frameworks."
        }

    agreements = parsed_synth.get("agreements", [])
    shared_objections = parsed_synth.get("shared_objections", [])
    disagreements = parsed_synth.get("disagreements_and_conflicts", [])
    blind_spots = parsed_synth.get("blind_spots_surfaced", [])
    dimensions = parsed_synth.get("contribution_dimensions", {})
    executive_verdict = parsed_synth.get("executive_verdict", "Multi-framework synthesis completed.")

    heading = "### 🏛️ Intellectual Rigour: Multi-Framework Synthesis & Contribution Audit"
    lines = [
        f"<!-- intellectual-rigour:start framework=\"rigour_synthesis\" source_hash=\"{source_hash}\" -->",
        heading,
        "",
        f"> **Epistemic Synthesis**: Evaluated across **{len(individual_artifacts)} Independent Frameworks** ({', '.join([get_framework(fid).name for fid in framework_ids if get_framework(fid)])})",
        f"> *Source Hash*: `{source_hash}`",
        "",
        f"**Executive Epistemic Verdict:**\n{executive_verdict}",
        ""
    ]

    if shared_objections:
        lines.append("#### 🔴 Convergent Critical Objections")
        for so in shared_objections:
            lines.append(f"- ⚠️ {so}")
        lines.append("")

    if agreements:
        lines.append("#### 🟢 Corroborated Methodological Strengths")
        for ag in agreements:
            lines.append(f"- ✅ {ag}")
        lines.append("")

    if disagreements:
        lines.append("#### ⚖️ Foundational Tensions & Disagreements")
        for d in disagreements:
            summary = d.get("conflict_summary", "Methodological Tension")
            fw_pair = d.get("frameworks_involved", "")
            cause = d.get("underlying_cause", "")
            impact = d.get("material_impact", "")
            lines.append(f"##### ⚔️ {summary} ({fw_pair})")
            if cause:
                lines.append(f"- **Underlying Divergence**: {cause}")
            if impact:
                lines.append(f"- **Research Impact**: {impact}")
            lines.append("")

    if blind_spots:
        lines.append("#### 🔍 Surfaced Paradigm Blind-Spots")
        for bs in blind_spots:
            lines.append(f"- 💡 {bs}")
        lines.append("")

    if dimensions:
        lines.append("#### 📊 Contribution Dimensions Assessment")
        for dim, eval_text in dimensions.items():
            clean_dim = dim.replace("_", " ").title()
            lines.append(f"- **{clean_dim}**: {eval_text}")
        lines.append("")

    lines.append("<!-- intellectual-rigour:end -->")
    formatted_md = "\n".join(lines)

    return ReviewArtifact(
        framework_id="rigour_synthesis",
        target_section_title=heading,
        operation="append_section",
        formatted_markdown=formatted_md,
        source_hash=source_hash,
        metadata={
            "participating_frameworks": framework_ids,
            "agreements_count": len(agreements),
            "shared_objections_count": len(shared_objections),
            "disagreements_count": len(disagreements),
            "source_hash": source_hash
        }
    )

def execute_intellectual_rigour_synthesis(
    report_text: str,
    topic: str = "",
    framework_ids: Optional[List[str]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    artifact = run_multi_framework_synthesis(
        report_text=report_text,
        topic=topic,
        requested_framework_ids=framework_ids,
        context=context
    )

    updated_report, was_replaced = patch_report_section(
        original_markdown=report_text,
        section_title=artifact.target_section_title,
        new_content=artifact.formatted_markdown
    )

    return {
        "success": True,
        "framework_id": artifact.framework_id,
        "new_section": artifact.formatted_markdown,
        "updated_report": updated_report,
        "was_in_place_replacement": was_replaced,
        "section_title": artifact.target_section_title,
        "source_hash": artifact.source_hash,
        "metadata": artifact.metadata
    }
