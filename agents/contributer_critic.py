from __future__ import annotations

from typing import List, Tuple


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
