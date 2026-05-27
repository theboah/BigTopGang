from __future__ import annotations

import json
from typing import List, Tuple

from agents.common import CritiqueResult, load_prompt, profile_step, run_structured_ollama


def validate_jobs(jobs: List[dict]) -> Tuple[List[dict], List[dict]]:
    approved = []
    rejected = []
    for job in jobs:
        if job.get("action") not in ("create", "update"):
            rejected.append({"job": job, "reason": "invalid action"})
            continue
        if not job.get("content") or len(job.get("content")) < 20:
            rejected.append({"job": job, "reason": "content too short"})
            continue
        approved.append(job)
    return approved, rejected


def validate_job(
    job: dict,
    article_text: str,
    transcript_text: str,
    vault_articles: List[str],
) -> CritiqueResult:
    prompt = load_prompt("contributer_critic_prompt.md")
    payload = {
        "job": job,
        "article_text": article_text,
        "transcript_excerpt": transcript_text[:5000],
        "vault_articles": vault_articles[:150],
    }

    passed = False
    message = ""
    try:
        with profile_step("contributor.critic_llm"):
            parsed = run_structured_ollama(f"{prompt}\n\nCONTEXT:\n{json.dumps(payload, indent=2, ensure_ascii=False)}", CritiqueResult)
        passed = bool(parsed.passed)
        message = parsed.message.strip()
    except Exception as exc:
        message = f"Critic unavailable: {exc}"

    if not passed:
        if not message:
            message = "Contribution rejected by critic."
        print(f"Contributor critic rejected article for {job.get('subject')}: {message}")

    return CritiqueResult(passed=passed, message=message)
