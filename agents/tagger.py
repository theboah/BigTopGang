from __future__ import annotations

import re
from typing import Iterable

from agents.tagger_critic import validate_tags
from tools.vault import ArticleType, get_all_article_names, get_article, update_article


def _article_type_tags(article_name: str) -> list[str]:
    folder = article_name.split("/")[0].lower()
    mapping = {
        "characters": "character",
        "creatures": "creature",
        "items": "item",
        "locations": "location",
        "events": "event",
        "factions": "faction",
    }
    tag = mapping.get(folder)
    return [tag] if tag else []


def _split_frontmatter(text: str) -> tuple[str, str, str]:
    match = re.match(r"^(---\s*\n.*?\n---\s*\n)(.*)$", text, re.DOTALL)
    if match:
        return match.group(1), match.group(2), ""
    return "", text, ""


def _merge_tags(frontmatter: str, tags: Iterable[str]) -> str:
    lines = frontmatter.splitlines()
    if not lines or lines[0].strip() != "---":
        combined = []
        for tag in [*tags, "bigtopgang"]:
            if tag and tag not in combined:
                combined.append(tag)
        return f"---\ntags: [{', '.join(combined)}]\n---"

    closing_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_index = index
            break
    if closing_index is None:
        closing_index = len(lines)

    body_lines = lines[1:closing_index]
    existing_tags: list[str] = []
    retained_lines: list[str] = []
    for line in body_lines:
        tag_match = re.match(r"^tags:\s*\[(.*?)\]\s*$", line.strip())
        if tag_match:
            existing_tags = [part.strip() for part in tag_match.group(1).split(",") if part.strip()]
            continue
        retained_lines.append(line)

    combined: list[str] = []
    for tag in [*existing_tags, *tags, "bigtopgang"]:
        if tag and tag not in combined:
            combined.append(tag)

    new_frontmatter_lines = ["---", f"tags: [{', '.join(combined)}]"]
    new_frontmatter_lines.extend(retained_lines)
    new_frontmatter_lines.append("---")
    return "\n".join(new_frontmatter_lines)


def tag_articles(subject_names: list[str]) -> list[dict]:
    article_names = [name for name in get_all_article_names() if not name.startswith("Summary/")]
    results: list[dict] = []

    for article_name in article_names:
        folder = article_name.split("/")[0]
        article_type = {
            "Characters": ArticleType.CHARACTER,
            "Creatures": ArticleType.CREATURE,
            "Items": ArticleType.ITEM,
            "Locations": ArticleType.LOCATION,
            "Events": ArticleType.EVENT,
            "Factions": ArticleType.FACTION,
        }.get(folder)
        if article_type is None:
            continue

        article_text = get_article(article_type, article_name.split("/", 1)[-1])
        frontmatter, body, _ = _split_frontmatter(article_text)
        if frontmatter:
            updated_frontmatter = _merge_tags(frontmatter, _article_type_tags(article_name))
            updated_text = f"{updated_frontmatter}\n{body}" if body else updated_frontmatter
        else:
            tags = [*_article_type_tags(article_name), "bigtopgang"]
            updated_text = f"---\ntags: [{', '.join(dict.fromkeys(tags))}]\n---\n\n{article_text.lstrip()}"

        critique = validate_tags(updated_text)
        if not critique.passed:
            print(f"Tagger rejected {article_name}: {critique.message}")
        if critique.passed and updated_text != article_text:
            update_article(article_type, article_name.split("/", 1)[-1], updated_text)
        results.append({"article": article_name, "passed": critique.passed, "message": critique.message})

    print(f"Tagger completed with {len(results)} articles reviewed")
    return results