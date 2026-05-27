from __future__ import annotations

import re

from agents.common import CritiqueResult


def validate_tags(text: str) -> CritiqueResult:
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not frontmatter_match:
        return CritiqueResult(passed=False, message="Missing YAML frontmatter.")

    frontmatter = frontmatter_match.group(1)
    if not re.search(r"^tags:\s*", frontmatter, re.MULTILINE):
        return CritiqueResult(passed=False, message="Missing tags field in frontmatter.")

    tag_lines = re.findall(r"^\s*-\s*(.+?)\s*$", frontmatter, re.MULTILINE)
    if not tag_lines:
        inline_tags = re.search(r"^tags:\s*\[(.*?)\]\s*$", frontmatter, re.MULTILINE)
        if not inline_tags:
            return CritiqueResult(passed=False, message="Tags field is not a valid list.")
        tag_lines = [part.strip() for part in inline_tags.group(1).split(",") if part.strip()]

    for tag in tag_lines:
        if not tag:
            return CritiqueResult(passed=False, message="Found an empty tag entry.")
        if tag.startswith("[") or tag.endswith("]"):
            return CritiqueResult(passed=False, message=f"Invalid tag formatting: {tag}")

    return CritiqueResult(passed=True, message="")