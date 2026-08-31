"""
Unit tests for living report section detection, in-place patching,
and markdown structure validation.
"""

import unittest
from backend.reports.sections import (
    find_markdown_sections,
    find_matching_section,
)
from backend.reports.patch import patch_report_section
from backend.reports.validation import validate_report_structure


SAMPLE_REPORT = """---
type: research_report
title: Solid State Batteries 2026
confidence: 0.95
---

# Deep Research Synthesis: Solid State Batteries

## Executive Summary
Solid state batteries offer high energy density and enhanced safety.

## Key Findings
- LLZO electrolytes exhibit high ionic conductivity [[src-paper_1]].
- Interfacial resistance remains a primary challenge [[src-paper_2]].

## Methodology & Verification
Truth Guard validated all claims against primary academic literature.

## Open Challenges
Dendrite penetration through ceramic grain boundaries.
"""


class TestMarkdownSectionParsing(unittest.TestCase):
    """Tests heading boundary identification."""

    def test_find_sections_extracts_all_headings(self):
        sections = find_markdown_sections(SAMPLE_REPORT)
        titles = [s.title for s in sections]
        self.assertIn("Executive Summary", titles)
        self.assertIn("Key Findings", titles)
        self.assertIn("Methodology & Verification", titles)
        self.assertIn("Open Challenges", titles)

    def test_code_fence_comments_are_not_treated_as_headings(self):
        code_markdown = """# System Architecture

## Implementation Details
Here is the backend implementation:
```python
# This is a python comment, not a markdown heading
def execute_task():
    # Another comment inside function
    return True
```

## Secondary Implementation
```javascript
// Javascript comment
## This should NOT be a heading
const x = 10;
```

## Performance Benchmarks
Latency is under 50ms.
"""
        sections = find_markdown_sections(code_markdown)
        titles = [s.title for s in sections]
        self.assertIn("System Architecture", titles)
        self.assertIn("Implementation Details", titles)
        self.assertIn("Secondary Implementation", titles)
        self.assertIn("Performance Benchmarks", titles)
        self.assertNotIn(
            "This is a python comment, not a markdown heading", titles
        )
        self.assertNotIn("This should NOT be a heading", titles)

    def test_multiple_fenced_blocks_and_unclosed_fence(self):
        unclosed_code_md = """# Title

## Section 1
```python
# Comment 1
x = 1
# Missing closing fence

## Section 2 (Inside unclosed fence)
y = 2
"""
        sections = find_markdown_sections(unclosed_code_md)
        titles = [s.title for s in sections]
        self.assertIn("Title", titles)
        self.assertIn("Section 1", titles)
        # Because the fence was not closed, Section 2 is safely treated as
        # part of the unclosed code block rather than corrupting boundaries
        self.assertNotIn("Section 2 (Inside unclosed fence)", titles)

    def test_matching_section_fuzzy_and_exact(self):
        sections = find_markdown_sections(SAMPLE_REPORT)
        # Exact match
        sec_exact = find_matching_section(sections, "Key Findings")
        self.assertIsNotNone(sec_exact)
        self.assertEqual(sec_exact.title, "Key Findings")

        # Fuzzy / case-insensitive match
        sec_fuzzy = find_matching_section(sections, "key findings")
        self.assertIsNotNone(sec_fuzzy)
        self.assertEqual(sec_fuzzy.title, "Key Findings")


class TestReportPatching(unittest.TestCase):
    """Tests in-place section replacement and content preservation."""

    def test_in_place_section_replacement_preserves_surrounding(self):
        new_key_findings = """## Key Findings
- 2026 Update: ALD alumina interlayers suppress dendritic growth [[src-paper_3]].
- Ionic conductivity reached 1.2 mS/cm at room temperature [[src-paper_4]]."""

        updated_report, was_replaced = patch_report_section(
            original_markdown=SAMPLE_REPORT,
            section_title="Key Findings",
            new_content=new_key_findings,
        )

        self.assertTrue(was_replaced)
        # Verify new content is present
        self.assertIn("ALD alumina interlayers suppress dendritic growth", updated_report)
        # Verify frontmatter is preserved
        self.assertIn("type: research_report", updated_report)
        # Verify other sections are untouched
        self.assertIn("## Executive Summary", updated_report)
        self.assertIn("Solid state batteries offer high energy density", updated_report)
        self.assertIn("## Open Challenges", updated_report)
        self.assertIn("Dendrite penetration through ceramic grain boundaries.", updated_report)

    def test_non_matching_section_appends_cleanly(self):
        new_section = """## Future Commercial Outlook
Mass production slated for automotive OEMs starting late 2027."""

        updated_report, was_replaced = patch_report_section(
            original_markdown=SAMPLE_REPORT,
            section_title="Future Commercial Outlook",
            new_content=new_section,
        )

        self.assertFalse(was_replaced)
        self.assertIn("## Future Commercial Outlook", updated_report)
        self.assertIn("## Executive Summary", updated_report)


class TestReportValidation(unittest.TestCase):
    """Tests markdown structural integrity rules."""

    def test_valid_report_passes(self):
        self.assertTrue(validate_report_structure(SAMPLE_REPORT))

    def test_unclosed_frontmatter_fails(self):
        broken = "---\ntype: report\nNo closing dashes\n# Title"
        self.assertFalse(validate_report_structure(broken))

    def test_unclosed_code_fence_fails(self):
        broken = "# Report\n```python\nprint('hello')\n# Missing closing fence"
        self.assertFalse(validate_report_structure(broken))


if __name__ == "__main__":
    unittest.main()
