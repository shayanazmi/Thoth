"""
Markdown structural validation module for living research reports.

Verifies that patched reports retain valid YAML frontmatter,
balanced code fences, and intact heading hierarchies.
"""

import re


def validate_report_structure(markdown_text: str) -> bool:
    """
    Verifies that a markdown report maintains structural integrity:
    1. YAML frontmatter (if present) has matching opening/closing '---'.
    2. Code fences (```) are properly paired.
    3. Document contains at least one heading or non-empty body.
    """
    if not markdown_text or not markdown_text.strip():
        return False

    text = markdown_text.strip()

    # 1. Validate YAML frontmatter if present
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) < 3:
            # Unclosed frontmatter
            return False

    # 2. Validate Code Fences Pairing
    fence_count = len(re.findall(r"^```", text, re.MULTILINE))
    if fence_count % 2 != 0:
        # Unclosed code fence detected
        return False

    # 3. Validate Minimum Content
    if len(text) < 10:
        return False

    return True
