"""
In-place section patching module for living markdown reports.

Replaces existing markdown sections in-place without corrupting YAML
frontmatter, citations, or unrelated sections.
"""

from typing import Tuple
from backend.reports.sections import (
    find_markdown_sections,
    find_matching_section,
)
from backend.reports.validation import validate_report_structure


def patch_report_section(
    original_markdown: str,
    section_title: str,
    new_content: str,
) -> Tuple[str, bool]:
    """
    Safely patches a section in original_markdown.

    If a matching section heading is found:
    - Replaces the exact line range of that section with new_content.
    - Preserves all surrounding sections, frontmatter, and citations.
    - Returns (updated_markdown, True).

    If no matching section is found:
    - Cleanly appends the new section to the bottom of the document.
    - Returns (updated_markdown, False).
    """
    if not original_markdown:
        return new_content.strip(), False

    clean_new_content = new_content.strip()
    sections = find_markdown_sections(original_markdown)
    matched_sec = find_matching_section(sections, section_title)

    if not matched_sec:
        # Fallback: Clean append
        separator = "\n\n" if not original_markdown.endswith("\n\n") else ""
        updated = f"{original_markdown.rstrip()}{separator}{clean_new_content}\n"
        return updated, False

    lines = original_markdown.splitlines()

    # Reconstruct document with the target section replaced
    before_lines = lines[: matched_sec.start_line]
    after_lines = lines[matched_sec.end_line + 1 :]

    new_section_lines = clean_new_content.splitlines()

    reconstructed_lines = before_lines + new_section_lines + after_lines
    updated_markdown = "\n".join(reconstructed_lines)

    # Validate structural integrity
    if not validate_report_structure(updated_markdown):
        # If patching produced invalid structure, revert to original + append
        updated_markdown = f"{original_markdown.rstrip()}\n\n{clean_new_content}\n"
        return updated_markdown, False

    return updated_markdown, True
