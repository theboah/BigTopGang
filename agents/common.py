from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from pydantic import BaseModel
from typing import Optional


class SummaryOutput(BaseModel):
    transcription_id: int
    summary: str


class SubjectsOutput(BaseModel):
    transcription_id: int
    subjects: list[str]


class ContributionJob(BaseModel):
    transcription_id: int
    subject: str
    action: str  # 'create' or 'update'
    target_type: Optional[str] = None
    target_path: Optional[str] = None
    content: Optional[str] = None


def load_prompt(prompt_filename: str) -> str:
    p = Path(__file__).parent / "prompts" / prompt_filename
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def get_ollama_runner(model: str = "gemma4") -> Callable[[str], str]:
    """Return a callable that runs the local Ollama model with a prompt and returns text.

    This is a simple subprocess wrapper around the `ollama` CLI. If `ollama` is not
    available the returned callable will raise RuntimeError when invoked.
    """

    def run(prompt: str) -> str:
        try:
            proc = subprocess.run(["ollama", "run", model, prompt], capture_output=True, text=True, check=True)
            return proc.stdout.strip()
        except FileNotFoundError:
            raise RuntimeError("ollama CLI not found; please install Ollama or provide an alternative LLM")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"LLM process failed: {exc}\nstdout: {exc.stdout}\nstderr: {exc.stderr}")

    return run
