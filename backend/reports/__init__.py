"""
Living Report Manipulation Package for Thoth.
Provides heading detection, safe in-place section patching,
and markdown structure validation.
"""

from backend.reports.sections import (
    MarkdownSection,
    find_markdown_sections,
    find_matching_section,
)
from backend.reports.patch import patch_report_section
from backend.reports.validation import validate_report_structure

__all__ = [
    "MarkdownSection",
    "find_markdown_sections",
    "find_matching_section",
    "patch_report_section",
    "validate_report_structure",
]
