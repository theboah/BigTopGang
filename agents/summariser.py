from __future__ import annotations

from agents.common import SummaryOutput, get_ollama_runner, load_prompt
from sqlite_tools import get_transcript


def summarise_session(transcription_id: int) -> SummaryOutput:
    transcript = get_transcript(transcription_id)
    text = transcript.get("text", "")

    prompt = load_prompt("summariser.md") or f"Summarise the following session transcript:\n\n{text[:4000]}"
    try:
        llm = get_ollama_runner()
        summary = llm(prompt)
    except Exception:
        # Fallback simple summary
        summary = text.strip()[:800]

    return SummaryOutput(transcription_id=transcription_id, summary=summary)
