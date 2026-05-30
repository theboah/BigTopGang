from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from agents.common import CritiqueResult
from agents.linker_critic import validate_links
from tools.vault import ArticleType, get_all_article_names, get_article, sanitize_target_path, update_article


def _article_type_from_folder(folder_name: str) -> Optional[ArticleType]:
    normalized = folder_name.rstrip("/").lower()
    mapping = {
        "characters": ArticleType.CHARACTER,
        "creatures": ArticleType.CREATURE,
        "items": ArticleType.ITEM,
        "locations": ArticleType.LOCATION,
        "events": ArticleType.EVENT,
        "factions": ArticleType.FACTION,
    }
    return mapping.get(normalized)


def _split_frontmatter(text: str) -> tuple[str, str, str]:
    match = re.match(r"^(---\s*\n.*?\n---\s*\n)(.*)$", text, re.DOTALL)
    if match:
        return match.group(1), match.group(2), ""
    return "", text, ""


def _protect_existing_links(line: str) -> tuple[str, dict[str, str]]:
    token_map: dict[str, str] = {}

    def _store(match: re.Match[str]) -> str:
        token = f"@@LINK_TOKEN_{len(token_map)}@@"
        token_map[token] = match.group(0)
        return token

    # Protect existing wiki links and markdown links from mention replacement.
    protected = re.sub(r"\[\[[^\]]+\]\]|\[[^\]]+\]\([^)]+\)", _store, line)
    return protected, token_map


def _restore_existing_links(line: str, token_map: dict[str, str]) -> str:
    restored = line
    for token, original in token_map.items():
        restored = restored.replace(token, original)
    return restored


def _replace_mentions(text: str, mention_map: dict[str, str], source_title: str) -> tuple[str, set[str]]:
    frontmatter, body, _ = _split_frontmatter(text)
    if not mention_map:
        return text, set()

    linked_targets: set[str] = set()
    source_basename = source_title.split("/")[-1].lower()
    lines = body.splitlines()
    output_lines: list[str] = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            output_lines.append(line)
            continue
        if in_code_block or stripped.startswith("#"):
            output_lines.append(line)
            continue

        protected_line, token_map = _protect_existing_links(line)
        updated_line = protected_line
        for subject_name in sorted(mention_map.keys(), key=len, reverse=True):
            target_path = mention_map[subject_name]
            target_basename = target_path.split("/")[-1].lower()
            if subject_name.lower() == source_title.lower() or target_basename == source_basename:
                continue

            link_target = target_path
            display_text = subject_name
            link = f"[[{link_target}|{display_text}]]"
            pattern = re.compile(rf"(?<!\[)\b{re.escape(subject_name)}\b(?!\])", re.IGNORECASE)

            def _sub(match: re.Match[str]) -> str:
                linked_targets.add(link_target)
                return link

            updated_line = pattern.sub(_sub, updated_line)

        output_lines.append(_restore_existing_links(updated_line, token_map))

    updated_body = "\n".join(output_lines)
    if body.endswith("\n"):
        updated_body += "\n"
    return f"{frontmatter}{updated_body}", linked_targets


def _append_related_section(text: str, related_links: Iterable[str]) -> str:
    related = [link for link in dict.fromkeys(related_links) if link]
    if not related:
        return text

    existing_section = re.search(r"(^## Related\s*\n)(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
    if existing_section:
        section_text = existing_section.group(2)
        current_links = set(re.findall(r"\[\[([^\]]+)\]\]", section_text))
        additions = []
        for link in related:
            if link not in current_links:
                additions.append(f"- [[{link}]]")
        if not additions:
            return text
        replacement = existing_section.group(1) + section_text.rstrip() + "\n" + "\n".join(additions) + "\n"
        return text[: existing_section.start()] + replacement + text[existing_section.end() :]

    related_block = "\n## Related\n\n" + "\n".join(f"- [[{link}]]" for link in related) + "\n"
    if text.endswith("\n"):
        return text + related_block.lstrip("\n")
    return text + related_block


def _build_target_map(article_names: Iterable[str]) -> dict[str, str]:
    stem_candidates: dict[str, list[str]] = defaultdict(list)
    for article_name in article_names:
        try:
            sanitize_target_path(article_name)
        except ValueError:
            continue
        stem = article_name.split("/")[-1].lower()
        stem_candidates[stem].append(article_name)

    target_map: dict[str, str] = {}
    for stem, candidates in stem_candidates.items():
        if len(candidates) == 1:
            target_map[stem] = candidates[0]
    return target_map


def link_articles(subject_names: list[str], max_passes: int = 2) -> list[dict]:
    article_names = [name for name in get_all_article_names() if not name.startswith("Summary/")]
    target_map = _build_target_map(article_names)
    article_types = {
        "Characters": ArticleType.CHARACTER,
        "Creatures": ArticleType.CREATURE,
        "Items": ArticleType.ITEM,
        "Locations": ArticleType.LOCATION,
        "Events": ArticleType.EVENT,
        "Factions": ArticleType.FACTION,
    }

    results: list[dict] = []
    for _ in range(max_passes):
        changed = False
        incoming_links: dict[str, set[str]] = defaultdict(set)
        article_text_cache: dict[str, str] = {}

        for article_name in article_names:
            folder = article_name.split("/")[0]
            article_type = article_types.get(folder)
            if article_type is None:
                continue

            article_text = get_article(article_type, article_name.split("/", 1)[-1])
            article_text_cache[article_name] = article_text
            updated_text, outgoing_links = _replace_mentions(article_text, target_map, article_name)
            for outgoing in outgoing_links:
                incoming_links[outgoing].add(article_name)

        for article_name, article_text in article_text_cache.items():
            folder = article_name.split("/")[0]
            article_type = article_types.get(folder)
            if article_type is None:
                continue

            updated_text, _ = _replace_mentions(article_text, target_map, article_name)
            updated_text = _append_related_section(updated_text, sorted(incoming_links.get(article_name, set())))
            if updated_text != article_text:
                critique = validate_links(updated_text, article_names)
                if critique.passed:
                    update_article(article_type, article_name.split("/", 1)[-1], updated_text)
                    changed = True
                else:
                    print(f"Linker rejected write for {article_name}: {critique.message}")
                    results.append({"article": article_name, "passed": False, "message": critique.message})

        if not changed:
            break

    for article_name in article_names:
        folder = article_name.split("/")[0]
        article_type = article_types.get(folder)
        if article_type is None:
            continue
        article_text = get_article(article_type, article_name.split("/", 1)[-1])
        critique = validate_links(article_text, article_names)
        if not critique.passed:
            print(f"Linker rejected {article_name}: {critique.message}")
        results.append({"article": article_name, "passed": critique.passed, "message": critique.message})

    print(f"Linker completed with {len(results)} articles reviewed")
    return results