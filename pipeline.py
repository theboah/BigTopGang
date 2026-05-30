import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

from sqlite_tools import create_transcript, get_transcript
from agents.summariser import build_summary_markdown, summarise_session
from agents.searcher import find_subjects
from typing import Optional

from agents.contributer import create_jobs_from_subjects_with_wiki_context, execute_jobs
from agents.linker import link_articles
from agents.tagger import tag_articles
from agents.common import format_profile_summary, reset_profile_events
from tools.fandom_wiki import fetch_wiki_context
from tools.vault import save_summary


# takes audio path and returns transcription id
def transcribe_audio(audio_path: str) -> int:
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("Missing GROQ_API_KEY. Add it to your .env file.")

    source_file = Path(audio_path)
    if not source_file.exists() or not source_file.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    client = Groq(api_key=api_key)
    with source_file.open("rb") as handle:
        transcription = client.audio.transcriptions.create(
            file=(source_file.name, handle.read()),
            model="whisper-large-v3",
            temperature=0,
            response_format="verbose_json",
        )

    transcript_text = getattr(transcription, "text", None)
    if not transcript_text:
        raise RuntimeError("Groq transcription returned no text.")

    transcription = create_transcript(text=transcript_text, source_path=str(source_file))
    return transcription["transcription_id"]


def summarise_session_step(transcription_id: int):
    return summarise_session(transcription_id)


def find_subjects_step(transcription_id: int):
    return find_subjects(transcription_id)


def contribute_to_vault_step(transcription_id: int, subjects: list, wiki_context_by_subject: Optional[dict] = None):
    jobs = create_jobs_from_subjects_with_wiki_context(transcription_id, subjects, wiki_context_by_subject)
    print(f"Contributor stage built {len(jobs)} approved jobs")
    results = execute_jobs(jobs)
    return jobs, results


def link_articles_step(subjects: list[str]):
    return link_articles(subjects)


def tag_articles_step(subjects: list[str]):
    return tag_articles(subjects)


def full_pipeline(audio_path: str):
    reset_profile_events()

    try:
        transcription_id = transcribe_audio(audio_path)
        print(f"Transcribed -> id={transcription_id}")
        print("Transcription section complete")

        summary = summarise_session_step(transcription_id)
        print(f"Summary: {summary.summary[:120]}")
        print("Summary generation complete")

        transcript_record = get_transcript(transcription_id)
        summary_markdown = build_summary_markdown(summary, transcript_record.get("source_path"))
        save_summary(f"session-{transcription_id}", summary_markdown)
        print("Summary saved")

        subjects = find_subjects_step(transcription_id)
        print(f"Subjects: {[subject.subject for subject in subjects]}")
        print("Subject extraction complete")

        wiki_context_by_subject = fetch_wiki_context([subject.subject for subject in subjects])
        print(f"Wiki context entries: {sum(len(entries) for entries in wiki_context_by_subject.values())}")

        jobs, results = contribute_to_vault_step(transcription_id, subjects, wiki_context_by_subject)
        print(f"Contribution results: {results}")
        print("Contribution section complete")

        link_results = link_articles_step([subject.subject for subject in subjects])
        print(f"Link results: {link_results}")
        print("Linking section complete")

        tag_results = tag_articles_step([subject.subject for subject in subjects])
        print(f"Tag results: {tag_results}")
        print("Tagging section complete")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        print(format_profile_summary())