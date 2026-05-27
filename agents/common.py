from __future__ import annotations

from contextlib import contextmanager
import re
import time
from pathlib import Path
from typing import Any, Iterator, Optional, TypeVar, TypedDict

from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from tools.vault import ArticleType


class SummaryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcription_id: int
    summary: str
    key_facts: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    notable_quotes: list[str] = Field(default_factory=list)
    safe_facts: list[str] = Field(default_factory=list)
    fallback: bool = False
    error: Optional[str] = None


class SubjectRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    subject_type: str
    evidence: str
    matched_article: Optional[str] = None
    confidence: Optional[str] = None
    action: Optional[str] = None


class SubjectsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcription_id: int
    subjects: list[SubjectRecord]


class ContributionJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcription_id: int
    subject: str
    subject_type: str
    action: str
    target_type: str
    target_path: str
    content: str
    source_article: Optional[str] = None


class CritiqueResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    message: str = ""


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class _StructuredState(TypedDict):
    prompt: str
    result: Any


_PROFILE_EVENTS: list[tuple[str, float]] = []


def reset_profile_events() -> None:
    _PROFILE_EVENTS.clear()


def record_profile_event(name: str, duration: float) -> None:
    _PROFILE_EVENTS.append((name, duration))


def get_profile_events() -> list[tuple[str, float]]:
    return list(_PROFILE_EVENTS)


def format_profile_summary() -> str:
    if not _PROFILE_EVENTS:
        return "Profiling summary: no events recorded"

    grouped: dict[str, list[float]] = {}
    for name, duration in _PROFILE_EVENTS:
        grouped.setdefault(name, []).append(duration)

    total = sum(duration for _, duration in _PROFILE_EVENTS)
    lines = ["Profiling summary:"]
    for name in sorted(grouped):
        durations = grouped[name]
        count = len(durations)
        subtotal = sum(durations)
        average = subtotal / count if count else 0.0
        minimum = min(durations)
        maximum = max(durations)
        percentage = (subtotal / total * 100.0) if total else 0.0
        lines.append(
            f"  - {name}: {subtotal:.3f}s total over {count} calls "
            f"(avg {average:.3f}s, min {minimum:.3f}s, max {maximum:.3f}s, {percentage:.1f}%)"
        )
    lines.append(f"  - total: {total:.3f}s")
    return "\n".join(lines)


@contextmanager
def profile_step(name: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        record_profile_event(name, time.perf_counter() - start)


def load_prompt(prompt_filename: str) -> str:
    prompt_dir = Path(__file__).parent / "prompts"
    candidates = [prompt_dir / prompt_filename]
    if not prompt_filename.endswith(".md"):
        candidates.append(prompt_dir / f"{prompt_filename}.md")
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return ""


def load_template(template_filename: str) -> str:
    template_path = Path(__file__).parent.parent / "templates" / template_filename
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    return ""


def _structured_schema_for_model(model_cls: type[StructuredModel]) -> dict[str, Any]:
    if model_cls is SummaryOutput:
        return {
            "type": "object",
            "properties": {
                "transcription_id": {"type": "integer"},
                "summary": {"type": "string"},
                "key_facts": {"type": "array", "items": {"type": "string"}},
                "subjects": {"type": "array", "items": {"type": "string"}},
                "notable_quotes": {"type": "array", "items": {"type": "string"}},
                "safe_facts": {"type": "array", "items": {"type": "string"}},
                "fallback": {"type": "boolean"},
                "error": {"type": ["string", "null"]},
            },
            "required": ["transcription_id", "summary"],
            "additionalProperties": False,
        }
    if model_cls is SubjectRecord:
        return {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "subject_type": {"type": "string"},
                "evidence": {"type": "string"},
                "matched_article": {"type": ["string", "null"]},
                "confidence": {"type": ["string", "null"]},
                "action": {"type": ["string", "null"]},
            },
            "required": ["subject", "subject_type", "evidence"],
            "additionalProperties": False,
        }
    if model_cls is SubjectsOutput:
        return {
            "type": "object",
            "properties": {
                "transcription_id": {"type": "integer"},
                "subjects": {
                    "type": "array",
                    "items": _structured_schema_for_model(SubjectRecord),
                },
            },
            "required": ["transcription_id", "subjects"],
            "additionalProperties": False,
        }
    if model_cls is ContributionJob:
        return {
            "type": "object",
            "properties": {
                "transcription_id": {"type": "integer"},
                "subject": {"type": "string"},
                "subject_type": {"type": "string"},
                "action": {"type": "string"},
                "target_type": {"type": "string"},
                "target_path": {"type": "string"},
                "content": {"type": "string"},
                "source_article": {"type": ["string", "null"]},
            },
            "required": ["transcription_id", "subject", "subject_type", "action", "target_type", "target_path", "content"],
            "additionalProperties": False,
        }
    if model_cls is CritiqueResult:
        return {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "message": {"type": "string"},
            },
            "required": ["passed", "message"],
            "additionalProperties": False,
        }
    raise ValueError(f"No structured schema registered for {model_cls.__name__}")


def run_structured_ollama(prompt: str, model_cls: type[StructuredModel], model: str = "gemma4") -> StructuredModel:
    """Run a LangGraph-backed Ollama call that returns a validated structured object."""

    structured_llm = ChatOllama(model=model).with_structured_output(
        _structured_schema_for_model(model_cls),
        method="json_schema",
    )

    def invoke_node(state: _StructuredState) -> dict:
        result = structured_llm.invoke(state["prompt"])
        return {"result": result}

    graph = StateGraph(_StructuredState)
    graph.add_node("invoke", invoke_node)
    graph.set_entry_point("invoke")
    graph.add_edge("invoke", END)
    app = graph.compile()

    output = app.invoke({"prompt": prompt})
    result = output["result"]
    if isinstance(result, model_cls):
        return result
    return model_cls.model_validate(result)


def format_article_catalog(article_names: list[str], limit: int = 120) -> str:
    selected = article_names[:limit]
    if not selected:
        return "(no existing articles)"
    return "\n".join(f"- {name}" for name in selected)


def normalize_article_type_name(value: str | None) -> str:
    if not value:
        return ArticleType.CHARACTER.value

    normalized = re.sub(r"[^a-z]+", "", value.strip().lower())
    aliases = {
        "character": ArticleType.CHARACTER.value,
        "characters": ArticleType.CHARACTER.value,
        "creature": ArticleType.CREATURE.value,
        "creatures": ArticleType.CREATURE.value,
        "item": ArticleType.ITEM.value,
        "items": ArticleType.ITEM.value,
        "faction": ArticleType.FACTION.value,
        "factions": ArticleType.FACTION.value,
        "location": ArticleType.LOCATION.value,
        "locations": ArticleType.LOCATION.value,
        "event": ArticleType.EVENT.value,
        "events": ArticleType.EVENT.value,
    }
    return aliases.get(normalized, ArticleType.CHARACTER.value)


def build_target_path(subject_type: str, subject_name: str) -> str:
    canonical = normalize_article_type_name(subject_type)
    folder = ArticleType(canonical).name.title() + "s"
    return f"{folder}/{subject_name}"
