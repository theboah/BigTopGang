from __future__ import annotations

from typing import List
from agents.contributer_critic import validate_jobs
from agents.common import ContributionJob
from tools.vault import get_all_article_names, insert_article, update_article, ArticleType


def create_jobs_from_subjects(transcription_id: int, subjects: List[str]) -> List[dict]:
    existing = get_all_article_names()
    existing_stems = {p.split("/")[-1] for p in existing}
    jobs: list[dict] = []
    for subj in subjects:
        action = "update" if subj in existing_stems else "create"
        content = f"# {subj}\n\nGenerated from transcription {transcription_id}."
        job = {
            "transcription_id": transcription_id,
            "subject": subj,
            "action": action,
            "target_type": ArticleType.CHARACTER.value,
            "content": content,
        }
        jobs.append(job)

    approved, rejected = validate_jobs(jobs)
    return approved


def execute_jobs(jobs: List[dict]) -> List[dict]:
    results = []
    for job in jobs:
        typ = ArticleType[job.get("target_type").upper()] if job.get("target_type") else ArticleType.CHARACTER
        if job.get("action") == "create":
            created = insert_article(typ, job.get("subject"), job.get("content"))
            results.append({"job": job, "created": created})
        else:
            updated = update_article(typ, job.get("subject"), job.get("content"))
            results.append({"job": job, "updated": updated})
    return results
