from __future__ import annotations

import enum
import re
from pathlib import Path
from pathlib import PurePosixPath
from typing import Iterable, List, Optional, Union

from langchain_core.tools import StructuredTool


class ArticleType(enum.Enum):
    CHARACTER = "character"
    ITEM = "item"
    CREATURE = "creature"
    FACTION = "faction"
    LOCATION = "location"
    EVENT = "event"


_INVALID_NAME_CHARS_RE = re.compile(r'[\[\]|<>:"?*]')


def sanitize_target_path(name: str) -> Path:
    if not isinstance(name, str):
        raise ValueError("Article name must be a string.")

    normalized = name.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("Article name cannot be empty.")
    if "[[" in normalized or "]]" in normalized:
        raise ValueError("Article name cannot contain wiki-link brackets.")
    if normalized.startswith("/"):
        raise ValueError("Article name cannot be absolute.")

    posix = PurePosixPath(normalized)
    if any(part in ("", ".", "..") for part in posix.parts):
        raise ValueError("Article name contains invalid path fragments.")

    for part in posix.parts:
        if _INVALID_NAME_CHARS_RE.search(part):
            raise ValueError(f"Article name contains invalid characters: {part}")

    return Path(*posix.parts)


def _default_vault_root() -> Path:
    return Path("vault")


def _vault_root(vault_path: Union[str, Path, None]) -> Path:
    return Path(vault_path) if vault_path is not None else _default_vault_root()


def _type_dir_name(article_type: ArticleType) -> str:
    return article_type.name.title() + "s"


def _article_type_root(vault_path: Union[str, Path, None], article_type: ArticleType) -> Path:
    return _vault_root(vault_path) / _type_dir_name(article_type)


def _normalize_article_name(article_name: str) -> Path:
    normalized = sanitize_target_path(article_name)
    if normalized.suffix.lower() == ".md":
        normalized = normalized.with_suffix("")
    return normalized


def _article_candidates(search_root: Path, article_name: str) -> Iterable[Path]:
    normalized_name = _normalize_article_name(article_name)
    target_stem = normalized_name.name
    target_relative = normalized_name.as_posix()

    for candidate in search_root.rglob("*.md"):
        relative_name = candidate.relative_to(search_root).with_suffix("").as_posix()
        if relative_name == target_relative or candidate.stem == target_stem:
            yield candidate


def _read_markdown_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_markdown_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _summary_root(vault_path: Union[str, Path, None]) -> Path:
    return _vault_root(vault_path) / "Summary"


def save_summary(
    summary_name: str,
    text: str,
    vault_path: Optional[str] = None,
) -> bool:
    summary_path = _summary_root(vault_path) / _normalize_article_name(summary_name)
    summary_path = summary_path.with_suffix(".md")
    _write_markdown_file(summary_path, text)
    return True


def get_all_summary_names(vault_path: Optional[str] = None) -> List[str]:
    return _get_articles_in_dir_and_sub_dir(_summary_root(vault_path))


def _get_articles_in_dir_and_sub_dir(path: Union[str, Path]) -> List[str]:
    root = Path(path)
    if not root.exists():
        return []
    names: list[str] = []
    for candidate in root.rglob("*.md"):
        relative_name = candidate.relative_to(root).with_suffix("").as_posix()
        try:
            sanitize_target_path(relative_name)
        except ValueError:
            continue
        names.append(relative_name)
    return sorted(names)


def get_all_article_names(vault_path: Optional[str] = None) -> List[str]:
    return _get_articles_in_dir_and_sub_dir(_vault_root(vault_path))


def get_all_article_names_for_type(
    article_type: ArticleType,
    vault_path: Optional[str] = None,
) -> List[str]:
    return _get_articles_in_dir_and_sub_dir(_article_type_root(vault_path, article_type))


def get_article(
    article_type: ArticleType,
    article_name: str,
    vault_path: Optional[str] = None,
) -> str:
    search_root = _article_type_root(vault_path, article_type)
    for candidate in _article_candidates(search_root, article_name):
        return _read_markdown_file(candidate)
    raise FileNotFoundError(f"Could not find article '{article_name}' under '{search_root}'")


def insert_article(
    article_type: ArticleType,
    name: str,
    text: str,
    vault_path: Optional[str] = None,
) -> bool:
    article_root = _article_type_root(vault_path, article_type)
    article_path = article_root / _normalize_article_name(name)
    article_path = article_path.with_suffix(".md")
    if article_path.exists():
        return False
    _write_markdown_file(article_path, text)
    return True


def upsert_article(
    article_type: ArticleType,
    name: str,
    text: str,
    vault_path: Optional[str] = None,
) -> bool:
    article_root = _article_type_root(vault_path, article_type)
    article_path = article_root / _normalize_article_name(name)
    article_path = article_path.with_suffix(".md")
    _write_markdown_file(article_path, text)
    return True


def update_article(
    article_type: ArticleType,
    name: str,
    newtext: str,
    vault_path: Optional[str] = None,
) -> bool:
    search_root = _article_type_root(vault_path, article_type)
    for candidate in _article_candidates(search_root, name):
        _write_markdown_file(candidate, newtext)
        return True
    return False


def get_links_for_article(
    article_type: ArticleType,
    article_name: str,
    vault_path: Optional[str] = None,
) -> List[str]:
    article_text = get_article(article_type, article_name, vault_path=vault_path)
    linked_targets: list[str] = []
    seen: set[str] = set()
    for match in re.findall(r"\[\[([^\]]+)\]\]", article_text):
        target = match.split("|", 1)[0].split("#", 1)[0].strip()
        if target and target not in seen:
            seen.add(target)
            linked_targets.append(target)
    return linked_targets


get_all_article_names_tool = StructuredTool.from_function(
    func=get_all_article_names,
    name="get_all_article_names",
    description="List all markdown article names in the vault.",
)

get_all_article_names_for_type_tool = StructuredTool.from_function(
    func=get_all_article_names_for_type,
    name="get_all_article_names_for_type",
    description="List all markdown article names under one article type folder in the vault.",
)

get_article_tool = StructuredTool.from_function(
    func=get_article,
    name="get_article",
    description="Read a markdown article from the vault.",
)

insert_article_tool = StructuredTool.from_function(
    func=insert_article,
    name="insert_article",
    description="Create a new markdown article in the vault when it does not already exist.",
)

upsert_article_tool = StructuredTool.from_function(
    func=upsert_article,
    name="upsert_article",
    description="Create or overwrite a markdown article in the vault.",
)

update_article_tool = StructuredTool.from_function(
    func=update_article,
    name="update_article",
    description="Overwrite an existing markdown article in the vault.",
)

get_links_for_article_tool = StructuredTool.from_function(
    func=get_links_for_article,
    name="get_links_for_article",
    description="Return the internal wiki links referenced by a markdown article.",
)

save_summary_tool = StructuredTool.from_function(
    func=save_summary,
    name="save_summary",
    description="Save a session summary markdown file in the vault Summary folder.",
)

get_all_summary_names_tool = StructuredTool.from_function(
    func=get_all_summary_names,
    name="get_all_summary_names",
    description="List all markdown summary names in the vault Summary folder.",
)


class Vault:
    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)

    def get_all_article_names(self) -> List[str]:
        return get_all_article_names(self.path)

    def get_all_article_names_for_type(self, article_type: ArticleType) -> List[str]:
        return get_all_article_names_for_type(article_type, self.path)

    def get_article(self, article_type: ArticleType, article_name: str) -> str:
        return get_article(article_type, article_name, self.path)

    def insert_article(self, article_type: ArticleType, name: str, text: str) -> bool:
        return insert_article(article_type, name, text, self.path)

    def upsert_article(self, article_type: ArticleType, name: str, text: str) -> bool:
        return upsert_article(article_type, name, text, self.path)

    def update_article(self, article_type: ArticleType, name: str, newtext: str) -> bool:
        return update_article(article_type, name, newtext, self.path)

    def get_links_for_article(self, article_type: ArticleType, article_name: str) -> List[str]:
        return get_links_for_article(article_type, article_name, self.path)

    def save_summary(self, summary_name: str, text: str) -> bool:
        return save_summary(summary_name, text, self.path)

    def get_all_summary_names(self) -> List[str]:
        return get_all_summary_names(self.path)

    def _get_articles_in_dir_and_sub_dir(self, path) -> List[str]:
        return _get_articles_in_dir_and_sub_dir(path)
