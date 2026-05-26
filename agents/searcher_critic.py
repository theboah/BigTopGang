from __future__ import annotations

from typing import Tuple, List

from tools.vault import get_all_article_names


def validate_subjects(subjects: List[str]) -> Tuple[List[str], List[str]]:
    """Return (approved, rejected).

    Simple heuristic: reject subjects that are stopwords or appear to be too short.
    Also deduplicate.
    """
    stopwords = {"The", "A", "An", "And", "Or", "Of"}
    approved: list[str] = []
    rejected: list[str] = []
    seen = set()
    for s in subjects:
        s = s.strip()
        if not s or len(s) < 3:
            rejected.append(s)
            continue
        if s in seen:
            rejected.append(s)
            continue
        seen.add(s)
        if s in stopwords:
            rejected.append(s)
            continue
        approved.append(s)
    return approved, rejected
