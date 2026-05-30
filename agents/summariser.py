from __future__ import annotations

import json

from agents.common import SummaryOutput, load_prompt, profile_step, run_structured_ollama
from sqlite_tools import get_transcript


def summarise_session(transcription_id: int) -> SummaryOutput:
    transcript = get_transcript(transcription_id)
    text = transcript.get("text", "")

    prompt = load_prompt("summariser_prompt.md") or "Summarise the transcript as structured JSON."
    with profile_step("summariser.prompt_build"):
        payload = {
            "transcription_id": transcription_id,
            "transcript": text[:4000],
        }
        request_prompt = f"{prompt}\n\nCONTEXT:\n{json.dumps(payload, indent=2, ensure_ascii=False)}"

    with profile_step("summariser.llm_call"):
        summary = run_structured_ollama(request_prompt, SummaryOutput)
    print(f"Summariser returned response ({len(summary.summary)} chars)")
    return summary


def build_summary_markdown(summary: SummaryOutput, source_path: Optional[str] = None) -> str:
    frontmatter_lines = ["---", f"transcription_id: {summary.transcription_id}"]
    if source_path:
        frontmatter_lines.append(f"source_path: {source_path}")
    frontmatter_lines.append("type: summary")
    frontmatter_lines.append("---")
    frontmatter = "\n".join(frontmatter_lines)

    sections = [f"# Session {summary.transcription_id} Summary", "", summary.summary.strip()]

    if summary.key_facts:
        sections.extend(["", "## Key Facts", ""])
        sections.extend(f"- {item}" for item in summary.key_facts)

    if summary.subjects:
        sections.extend(["", "## Subjects", ""])
        sections.extend(f"- {item}" for item in summary.subjects)

    if summary.notable_quotes:
        sections.extend(["", "## Notable Quotes", ""])
        sections.extend(f"- {item}" for item in summary.notable_quotes)

    if summary.safe_facts:
        sections.extend(["", "## Safe Facts", ""])
        sections.extend(f"- {item}" for item in summary.safe_facts)

    return f"{frontmatter}\n\n" + "\n".join(sections).rstrip() + "\n"
