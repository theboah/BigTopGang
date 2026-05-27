from __future__ import annotations

import json
from typing import Iterable

from agents.common import CritiqueResult, SubjectRecord, load_prompt, profile_step, run_structured_ollama


def _subject_to_dict(subject: SubjectRecord | dict) -> dict:
    if isinstance(subject, SubjectRecord):
        return subject.model_dump()
    return dict(subject)


def validate_subjects(
    transcript_text: str,
    subjects: list[SubjectRecord | dict],
    vault_articles: Iterable[str],
    max_excerpt_chars: int = 4000,
) -> CritiqueResult:
    prompt = load_prompt("searcher_critic_prompt.md")
    subject_payload = [_subject_to_dict(subject) for subject in subjects]
    context = {
        "transcript_excerpt": transcript_text[:max_excerpt_chars],
        "subjects": subject_payload,
        "vault_articles": list(vault_articles)[:150],
    }
    payload_text = json.dumps(context, indent=2, ensure_ascii=False)

    passed = False
    message = ""
    try:
        with profile_step("searcher.critic_llm"):
            parsed = run_structured_ollama(f"{prompt}\n\nCONTEXT:\n{payload_text}", CritiqueResult)
        passed = bool(parsed.passed)
        message = parsed.message.strip()
    except Exception as exc:
        message = f"Critic unavailable: {exc}"

    if not passed:
        if not message:
            message = "Extraction rejected by critic."
        print(f"Searcher critic rejected extraction: {message}")

    return CritiqueResult(passed=passed, message=message)
