from __future__ import annotations

import json
from typing import List

from agents.common import SubjectRecord, SubjectsOutput, format_article_catalog, load_prompt, profile_step, run_structured_ollama
from agents.searcher_critic import validate_subjects
from sqlite_tools import get_transcript
from tools.vault import get_all_article_names


def _subject_key(subject: SubjectRecord) -> str:
    return " ".join(subject.subject.strip().casefold().split())


def _dedupe_subjects(subjects: list[SubjectRecord]) -> list[SubjectRecord]:
    deduped: list[SubjectRecord] = []
    seen: dict[str, SubjectRecord] = {}

    for subject in subjects:
        key = _subject_key(subject)
        existing = seen.get(key)
        if existing is None:
            seen[key] = subject
            deduped.append(subject)
            continue

        if not existing.evidence and subject.evidence:
            existing.evidence = subject.evidence
        if not existing.matched_article and subject.matched_article:
            existing.matched_article = subject.matched_article
        if not existing.confidence and subject.confidence:
            existing.confidence = subject.confidence
        if not existing.action and subject.action:
            existing.action = subject.action

    return deduped


def _run_searcher_prompt(transcription_id: int, text: str, vault_articles: list[str]) -> List[SubjectRecord]:
    with profile_step("searcher.prompt_build"):
        prompt = load_prompt("searcher_prompt.md")
        article_catalog = format_article_catalog(vault_articles)
        payload = {
            "transcription_id": transcription_id,
            "transcript": text,
            "vault_articles": article_catalog,
        }
        prompt_text = f"{prompt}\n\nCONTEXT:\n{json.dumps(payload, indent=2, ensure_ascii=False)}"

    with profile_step("searcher.llm_call"):
        parsed = run_structured_ollama(prompt_text, SubjectsOutput)
    if parsed.transcription_id != transcription_id:
        raise ValueError("Searcher returned the wrong transcription_id.")
    deduped_subjects = _dedupe_subjects(parsed.subjects)
    print(f"Searcher returned response ({len(deduped_subjects)} subjects)")
    return deduped_subjects


def find_subjects(transcription_id: int, max_retries: int = 3) -> List[SubjectRecord]:
    transcript = get_transcript(transcription_id)
    text = transcript.get("text", "")
    vault_articles = get_all_article_names()

    final_subjects: list[SubjectRecord] = []
    attempt = 0
    while attempt < max_retries:
        candidates = _run_searcher_prompt(transcription_id, text, vault_articles)

        with profile_step("searcher.critic_call"):
            critique = validate_subjects(text, candidates, vault_articles, transcription_id=transcription_id)
        if critique.passed:
            final_subjects = _dedupe_subjects(candidates)
            break

        final_subjects = _dedupe_subjects(candidates)
        attempt += 1

    if not final_subjects:
        raise RuntimeError("Searcher did not produce any valid subjects.")

    print(f"Searcher completed with subjects: {[subject.subject for subject in final_subjects]}")
    return final_subjects
