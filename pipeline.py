import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

from sqlite_tools import create_transcript
from agents.summariser import summarise_session
from agents.searcher import find_subjects
from agents.contributer import create_jobs_from_subjects, execute_jobs


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


def contribute_to_vault_step(transcription_id: int, subjects: list):
    jobs = create_jobs_from_subjects(transcription_id, subjects)
    results = execute_jobs(jobs)
    return results


def full_pipeline(audio_path: str):
    try:
        transcription_id = transcribe_audio(audio_path)
        print(f"Transcribed -> id={transcription_id}")
        summary = summarise_session_step(transcription_id)
        print(f"Summary: {summary.summary[:120]}")
        subjects = find_subjects_step(transcription_id)
        print(f"Subjects: {subjects}")
        results = contribute_to_vault_step(transcription_id, subjects)
        print(f"Contribution results: {results}")
    except Exception as e:
        print(f"An error occurred: {e}")