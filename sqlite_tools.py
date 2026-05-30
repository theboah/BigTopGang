from __future__ import annotations

from typing import Optional
from typing import List

from langchain_core.tools import StructuredTool

from models.db import get_session, init_db
from models.transcript import Transcript


init_db()


def create_transcript(text: str, source_path: Optional[str] = None) -> dict:
    with get_session() as session:
        transcript = Transcript(text=text, source_path=source_path)
        session.add(transcript)
        session.flush()
        session.refresh(transcript)
        transcript_data = transcript.to_dict()

    try:
        from tools.chroma_store import index_transcript_record

        index_transcript_record(transcript_data)
    except Exception as exc:
        print(f"Transcript semantic index skipped: {exc}")

    return transcript_data


def get_transcript(transcription_id: int) -> dict:
    with get_session() as session:
        transcript = session.get(Transcript, transcription_id)
        if transcript is None:
            raise FileNotFoundError(f"Transcript {transcription_id} not found")
        return transcript.to_dict()


def list_transcripts(limit: int = 50) -> List[dict]:
    with get_session() as session:
        transcripts = (
            session.query(Transcript)
            .order_by(Transcript.transcription_id.desc())
            .limit(limit)
            .all()
        )
        return [transcript.to_dict() for transcript in transcripts]


def update_transcript(transcription_id: int, text: str) -> dict:
    with get_session() as session:
        transcript = session.get(Transcript, transcription_id)
        if transcript is None:
            raise FileNotFoundError(f"Transcript {transcription_id} not found")
        transcript.text = text
        session.flush()
        session.refresh(transcript)
        transcript_data = transcript.to_dict()

    try:
        from tools.chroma_store import index_transcript_record

        index_transcript_record(transcript_data)
    except Exception as exc:
        print(f"Transcript semantic reindex skipped: {exc}")

    return transcript_data


def delete_transcript(transcription_id: int) -> bool:
    with get_session() as session:
        transcript = session.get(Transcript, transcription_id)
        if transcript is None:
            return False
        session.delete(transcript)

    try:
        from tools.chroma_store import delete_transcript_index

        delete_transcript_index(transcription_id)
    except Exception as exc:
        print(f"Transcript semantic delete skipped: {exc}")

    return True


create_transcript_tool = StructuredTool.from_function(
    func=create_transcript,
    name="create_transcript",
    description="Create a transcript record in the SQLite database.",
)

get_transcript_tool = StructuredTool.from_function(
    func=get_transcript,
    name="get_transcript",
    description="Fetch a transcript record by transcription id.",
)

list_transcripts_tool = StructuredTool.from_function(
    func=list_transcripts,
    name="list_transcripts",
    description="List transcript records from newest to oldest.",
)

update_transcript_tool = StructuredTool.from_function(
    func=update_transcript,
    name="update_transcript",
    description="Update the text of an existing transcript record.",
)

delete_transcript_tool = StructuredTool.from_function(
    func=delete_transcript,
    name="delete_transcript",
    description="Delete a transcript record from the SQLite database.",
)