from typing import Dict, Any, Optional

from backend.intellectual_rigour.models import (
    ReviewTarget,
    ReviewRequest,
    CritiqueFinding,
    ThinkerOutput,
    ReviewArtifact,
    ReasoningSpec,
)
from backend.intellectual_rigour.registry import (
    resolve_thinker_command,
    get_framework,
    list_registered_thinkers,
)
from backend.intellectual_rigour.attack_surface import (
    detect_attack_surfaces,
    AttackSurfaceProfile,
)
from backend.intellectual_rigour.synthesis import (
    run_multi_framework_synthesis,
    execute_intellectual_rigour_synthesis,
)
from backend.reports.patch import patch_report_section

def execute_thinker_review(
    query: str,
    report_text: str,
    topic: str = "",
    context: dict = None,
) -> dict:
    resolved = resolve_thinker_command(query)
    if not resolved:
        return {
            "success": False,
            "error": f"No reasoning framework recognized for query: '{query}'",
        }

    target_obj, request = resolved

    if target_obj == "rigour_synthesis":
        return execute_intellectual_rigour_synthesis(
            report_text=report_text,
            topic=topic,
            context=context
        )

    framework = target_obj
    source_hash = framework.compute_source_hash(report_text)

    artifact: ReviewArtifact = framework.review(
        request=request,
        report_text=report_text,
        topic=topic,
        context=context,
    )

    updated_report, was_replaced = patch_report_section(
        original_markdown=report_text,
        section_title=artifact.target_section_title,
        new_content=artifact.formatted_markdown,
    )

    return {
        "success": True,
        "framework_id": framework.id,
        "thinker_name": framework.name,
        "new_section": artifact.formatted_markdown,
        "updated_report": updated_report,
        "was_in_place_replacement": was_replaced,
        "section_title": artifact.target_section_title,
        "source_hash": source_hash,
        "metadata": artifact.metadata,
    }

__all__ = [
    "ReviewTarget",
    "ReviewRequest",
    "CritiqueFinding",
    "ThinkerOutput",
    "ReviewArtifact",
    "ReasoningSpec",
    "resolve_thinker_command",
    "get_framework",
    "list_registered_thinkers",
    "detect_attack_surfaces",
    "AttackSurfaceProfile",
    "run_multi_framework_synthesis",
    "execute_intellectual_rigour_synthesis",
    "execute_thinker_review",
]
