from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _ensure_fanboa_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    candidate = repo_root.parents[1] / "fanboa"
    if candidate.exists():
        candidate_text = str(candidate)
        if candidate_text not in sys.path:
            sys.path.insert(0, candidate_text)


_ensure_fanboa_on_path()

try:
    from fanboa.fandom_api import FandomApiClient, FandomApiError
except Exception:  # pragma: no cover - optional dependency fallback
    FandomApiClient = None  # type: ignore[assignment]

    class FandomApiError(RuntimeError):
        pass


def _normalize_key(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _configured_wiki_reference() -> str:
    for key in ("FANDOM_WIKI_URL", "FANDOM_WIKI", "FANDOM_WIKI_NAME"):
        value = os.getenv(key, "").strip()
        if value:
            return value
    return "https://forgottenrealms.fandom.com"


@lru_cache(maxsize=1)
def _client() -> Optional[FandomApiClient]:
    if FandomApiClient is None:
        return None
    return FandomApiClient()


def _candidate_titles(subject_name: str) -> list[str]:
    raw = subject_name.strip()
    if not raw:
        return []

    candidates = [raw]
    if "/" in raw:
        candidates.append(raw.split("/", 1)[-1].strip())
    if "_" in raw:
        candidates.append(raw.replace("_", " "))

    words = [part for part in raw.replace("_", " ").split() if part]
    if words:
        candidates.append(" ".join(word.capitalize() for word in words))

    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        cleaned = candidate.strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            unique.append(cleaned)
    return unique


def _page_context_for_subject(wiki: str, subject_name: str) -> Optional[Dict[str, Any]]:
    client = _client()
    if client is None:
        return None

    for candidate_title in _candidate_titles(subject_name):
        try:
            page = client.get_page(wiki, candidate_title, include_wikitext=False)
        except FandomApiError:
            continue
        except Exception:
            continue

        if not page:
            continue

        title = page.get("title") or candidate_title
        url = page.get("fullurl") or page.get("canonicalurl") or ""
        excerpt = str(page.get("extract") or "").strip()

        related_titles: list[str] = []
        try:
            related_titles = client.get_page_links(wiki, title, limit=8)
        except Exception:
            related_titles = []

        return {
            "subject": subject_name,
            "title": title,
            "url": url,
            "excerpt": excerpt[:1200],
            "related_titles": related_titles[:8],
        }

    return None


def fetch_wiki_context(subject_names: Iterable[str], max_subjects: int = 12) -> Dict[str, List[Dict[str, Any]]]:
    wiki_reference = _configured_wiki_reference()
    client = _client()
    if client is None:
        return {}

    contexts: Dict[str, List[Dict[str, Any]]] = {}
    for subject_name in list(dict.fromkeys(subject_names))[:max_subjects]:
        subject = subject_name.strip()
        if not subject:
            continue

        context = _page_context_for_subject(wiki_reference, subject)
        if context is None:
            continue

        contexts.setdefault(_normalize_key(subject), []).append(context)

    return contexts


def format_wiki_context(wiki_context: Dict[str, List[Dict[str, Any]]], subject_names: Iterable[str]) -> str:
    ordered_entries: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()

    for subject_name in subject_names:
        key = _normalize_key(subject_name)
        for context in wiki_context.get(key, []):
            dedupe_key = (context.get("title", ""), context.get("url", ""))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            ordered_entries.append(context)

    if not ordered_entries:
        return "(no fandom wiki context available)"

    return json.dumps(ordered_entries, indent=2, ensure_ascii=False)