from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from agents.common import (
    ContributionJob,
    SubjectRecord,
    build_target_path,
    load_prompt,
    load_template,
    normalize_article_type_name,
    profile_step,
    run_structured_ollama,
)
from agents.contributer_critic import validate_job, validate_jobs
from sqlite_tools import get_transcript
from tools.vault import ArticleType, get_all_article_names, get_all_article_names_for_type, get_article, upsert_article


def _subject_from_value(subject: SubjectRecord | dict | str) -> SubjectRecord:
    if isinstance(subject, SubjectRecord):
        return subject
    if isinstance(subject, str):
        return SubjectRecord(subject=subject, subject_type="character", evidence=subject)
    return SubjectRecord(
        subject=str(subject.get("subject", subject.get("name", ""))).strip(),
        subject_type=str(subject.get("subject_type", subject.get("type", "character"))).strip(),
        evidence=str(subject.get("evidence", "")).strip(),
        matched_article=str(subject.get("matched_article")).strip() if subject.get("matched_article") else None,
        confidence=str(subject.get("confidence")).strip() if subject.get("confidence") else None,
        action=str(subject.get("action")).strip() if subject.get("action") else None,
    )


def _resolve_article_type(subject_type: str, target_name: str | None = None) -> ArticleType:
    if target_name:
        target_name_lower = target_name.lower()
        if target_name_lower.startswith("characters/"):
            return ArticleType.CHARACTER
        if target_name_lower.startswith("creatures/"):
            return ArticleType.CREATURE
        if target_name_lower.startswith("items/"):
            return ArticleType.ITEM
        if target_name_lower.startswith("locations/"):
            return ArticleType.LOCATION
        if target_name_lower.startswith("events/"):
            return ArticleType.EVENT
        if target_name_lower.startswith("factions/"):
            return ArticleType.FACTION
    return ArticleType[normalize_article_type_name(subject_type).upper()]


def _find_existing_article(subject: SubjectRecord, existing_articles: Iterable[str]) -> str | None:
    subject_name = subject.subject.strip().lower()
    for article_name in existing_articles:
        normalized = article_name.lower()
        if normalized == subject_name or Path(article_name).stem.lower() == subject_name:
            return article_name
    if subject.matched_article:
        matched = subject.matched_article.strip()
        if matched in set(existing_articles):
            return matched
    return None


def _build_article_prompt(
    transcription_id: int,
    subject: SubjectRecord,
    transcript_text: str,
    vault_articles: list[str],
    current_article_text: str,
    target_type: ArticleType,
    target_path: str,
) -> str:
    with profile_step("contributor.prompt_build"):
        prompt = load_prompt("contributer_prompt.md")
        template_name = f"{target_type.value}.md"
        subject_template = load_template(template_name)
        payload = {
            "transcription_id": transcription_id,
            "subject": subject.model_dump(),
            "target_type": target_type.value,
            "target_path": target_path,
            "article_template": subject_template,
            "transcript_excerpt": transcript_text[:6000],
            "current_article_text": current_article_text,
        }
        return f"{prompt}\n\nCONTEXT:\n{json.dumps(payload, indent=2, ensure_ascii=False)}"


def _generate_article_content(
    transcription_id: int,
    subject: SubjectRecord,
    transcript_text: str,
    vault_articles: list[str],
    current_article_text: str,
    target_type: ArticleType,
    target_path: str,
) -> str:
    prompt_text = _build_article_prompt(
        transcription_id,
        subject,
        transcript_text,
        vault_articles,
        current_article_text,
        target_type,
        target_path,
    )
    with profile_step("contributor.llm_call"):
        parsed = run_structured_ollama(prompt_text, ContributionJob)
    print(f"Contributor returned response for {subject.subject} ({len(parsed.content)} chars)")
    if parsed.transcription_id != transcription_id:
        raise ValueError("Contributor returned the wrong transcription_id.")
    if parsed.subject.strip().lower() != subject.subject.strip().lower():
        raise ValueError("Contributor returned the wrong subject.")
    if normalize_article_type_name(parsed.target_type) != target_type.value:
        raise ValueError("Contributor returned the wrong target_type.")
    if parsed.target_path.strip() != target_path.strip():
        raise ValueError("Contributor returned the wrong target_path.")
    return parsed.content


def _build_job_for_subject(
    transcription_id: int,
    subject: SubjectRecord,
    transcript_text: str,
    vault_articles: list[str],
    max_retries: int = 3,
) -> dict | None:
    target_type = _resolve_article_type(subject.subject_type, subject.matched_article)
    typed_articles = get_all_article_names_for_type(target_type)
    existing_article = _find_existing_article(subject, typed_articles)
    target_path = existing_article or build_target_path(target_type.value, subject.subject)
    current_article_text = ""
    action = "create"

    if existing_article:
        action = "update"
        with profile_step("contributor.read_current_article"):
            try:
                current_article_text = get_article(target_type, subject.subject)
            except Exception:
                current_article_text = ""

    last_content = ""
    for _ in range(max_retries):
        try:
            content = _generate_article_content(
                transcription_id,
                subject,
                transcript_text,
                vault_articles,
                current_article_text,
                target_type,
                target_path,
            )
        except Exception as exc:
            print(f"Contributor generation failed for {subject.subject}: {exc}")
            continue

        critique = validate_job(
            {
                "transcription_id": transcription_id,
                "subject": subject.subject,
                "subject_type": target_type.value,
                "action": action,
                "target_type": target_type.value,
                "target_path": target_path,
                "content": content,
                "source_article": existing_article,
                "subject_record": subject.model_dump(),
                "current_article_text": current_article_text,
            },
            content,
            transcript_text,
            vault_articles,
        )
        if critique.passed:
            return {
                "transcription_id": transcription_id,
                "subject": subject.subject,
                "subject_type": target_type.value,
                "action": action,
                "target_type": target_type.value,
                "target_path": target_path,
                "content": content,
                "source_article": existing_article,
            }

    return None


def create_jobs_from_subjects(transcription_id: int, subjects: List[SubjectRecord | dict | str]) -> List[dict]:
    transcript = get_transcript(transcription_id)
    transcript_text = transcript.get("text", "")
    existing = get_all_article_names()

    jobs: list[dict] = []
    for subject_value in subjects:
        subject = _subject_from_value(subject_value)
        if not subject.subject:
            continue
        job = _build_job_for_subject(transcription_id, subject, transcript_text, existing)
        if job is not None:
            jobs.append(job)

    approved, rejected = validate_jobs(jobs)
    if rejected:
        print(f"Contributor rejected jobs: {rejected}")
    print(f"Contributor completed with {len(approved)} approved jobs")
    return approved


def execute_jobs(jobs: List[dict]) -> List[dict]:
    results = []
    for job in jobs:
        typ = _resolve_article_type(job.get("subject_type", job.get("target_type", "character")))
        written = upsert_article(typ, job.get("subject"), job.get("content"))
        results.append({"job": job, "written": written})
    print(f"Contributor executed {len(results)} jobs")
    return results
