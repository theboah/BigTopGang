from __future__ import annotations

import re
from pathlib import Path
from typing import List

from agents.searcher_critic import validate_subjects
from sqlite_tools import get_transcript
from tools.vault import get_all_article_names


def _extract_candidates_from_text(text: str, max_candidates: int = 20) -> List[str]:
    # heuristic: Titlecase sequences (e.g., 'The WitchLight Carnival')
    pattern = r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b"
    matches = re.findall(pattern, text)
    unique = []
    seen = set()
    for m in matches:
        if m in seen:
            continue
        seen.add(m)
        unique.append(m)
        if len(unique) >= max_candidates:
            break
    return unique


def find_subjects(transcription_id: int, max_retries: int = 3) -> List[str]:
    transcript = get_transcript(transcription_id)
    text = transcript.get("text", "")
    vault_articles = get_all_article_names()

    attempt = 0
    candidates: List[str] = []
    approved: List[str] = []
    while attempt < max_retries:
        candidates = _extract_candidates_from_text(text)
        approved, rejected = validate_subjects(candidates)
        # If we have any approved subjects, accept them; otherwise retry
        if approved:
            break
        attempt += 1
    # remove any subjects that exactly match existing vault article tail names
    existing_tails = {Path(p).stem for p in vault_articles}
    final = [s for s in approved if s not in existing_tails]
    return final
