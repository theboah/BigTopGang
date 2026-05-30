from __future__ import annotations

import json
from typing import List, Optional, Tuple

from agents.common import CritiqueResult, load_prompt, profile_step, run_structured_ollama
from tools.chroma_store import build_semantic_context
from tools.fandom_wiki import fetch_wiki_context, format_wiki_context


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
    transcription_id: Optional[int] = None,
) -> CritiqueResult:
    prompt = load_prompt("contributer_critic_prompt.md")
    semantic_transcription_id = transcription_id if transcription_id is not None else job.get("transcription_id")
    subject_name = str(job.get("subject", "")).strip()
    wiki_context_by_subject = fetch_wiki_context([subject_name] if subject_name else [])
    payload = {
        "job": job,
        "article_text": article_text,
        "transcript_excerpt": transcript_text[:5000],
        "vault_articles": vault_articles[:150],
        "semantic_context": build_semantic_context(
            int(semantic_transcription_id) if semantic_transcription_id is not None else None,
            [job.get("subject", ""), job.get("target_path", ""), article_text[:800]],
        ),
        "wiki_context": format_wiki_context(wiki_context_by_subject, [subject_name] if subject_name else []),
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
