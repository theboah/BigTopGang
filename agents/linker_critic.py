from __future__ import annotations

import re
from typing import Iterable

from agents.common import CritiqueResult


def _known_name_set(article_names: Iterable[str]) -> set[str]:
    known = set()
    for article_name in article_names:
        known.add(article_name.lower())
        known.add(article_name.split("/")[-1].lower())
    return known


def validate_links(text: str, article_names: Iterable[str]) -> CritiqueResult:
    known = _known_name_set(article_names)
    for match in re.findall(r"\[\[([^\]]+)\]\]", text):
        target = match.split("|", 1)[0].split("#", 1)[0].strip()
        if not target:
            return CritiqueResult(passed=False, message="Found an empty wiki link target.")
        target_lower = target.lower()
        if target_lower not in known and target_lower.split("/")[-1] not in known:
            return CritiqueResult(passed=False, message=f"Missing wiki link target: {target}")
    if "[[" in text and "]]" not in text:
        return CritiqueResult(passed=False, message="Malformed wiki link brackets found.")
    return CritiqueResult(passed=True, message="")