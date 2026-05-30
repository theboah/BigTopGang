from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, List, Optional

try:
    import chromadb
except Exception:  # pragma: no cover - optional dependency fallback
    chromadb = None  # type: ignore[assignment]

try:
    from langchain_ollama import OllamaEmbeddings
except Exception:  # pragma: no cover - optional dependency fallback
    OllamaEmbeddings = None  # type: ignore[assignment]


BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BASE_DIR / "chroma_store"
COLLECTION_NAME = "transcripts"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "embeddinggemma")


def _normalize_query_text(text: str) -> str:
    return " ".join(text.strip().split())


def _chunk_text(text: str, chunk_size: int = 1600, overlap: int = 200) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []

    if chunk_size <= 0:
        return [cleaned]

    overlap = max(0, min(overlap, chunk_size - 1))
    chunks: list[str] = []
    start = 0

    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)

    return chunks


@lru_cache(maxsize=1)
def _embedding_model() -> Optional[OllamaEmbeddings]:
    if OllamaEmbeddings is None:
        return None
    return OllamaEmbeddings(model=EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def _client() -> Optional[Any]:
    if chromadb is None:
        return None
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def _collection() -> Optional[Any]:
    client = _client()
    if client is None:
        return None
    return client.get_or_create_collection(name=COLLECTION_NAME)


def _embed_documents(texts: list[str]) -> list[list[float]]:
    model = _embedding_model()
    if model is None:
        raise RuntimeError("Ollama embeddings are unavailable.")
    return model.embed_documents(texts)


def _embed_query(text: str) -> list[float]:
    model = _embedding_model()
    if model is None:
        raise RuntimeError("Ollama embeddings are unavailable.")
    return model.embed_query(text)


def index_transcript_record(transcript: dict, chunk_size: int = 1600, overlap: int = 200) -> int:
    collection = _collection()
    if collection is None:
        return 0

    transcription_id = int(transcript["transcription_id"])
    text = str(transcript.get("text", ""))
    source_path = transcript.get("source_path")
    chunks = _chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    try:
        collection.delete(where={"transcription_id": transcription_id})
    except Exception:
        pass

    if not chunks:
        return 0

    embeddings = _embed_documents(chunks)
    ids = [f"{transcription_id}:{index}" for index in range(len(chunks))]
    metadatas = [
        {
            "transcription_id": transcription_id,
            "chunk_index": index,
            "source_path": source_path or "",
            "chunk_size": len(chunk),
        }
        for index, chunk in enumerate(chunks)
    ]
    collection.upsert(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)
    return len(chunks)


def index_transcript(transcription_id: int, chunk_size: int = 1600, overlap: int = 200) -> int:
    from sqlite_tools import get_transcript

    transcript = get_transcript(transcription_id)
    return index_transcript_record(transcript, chunk_size=chunk_size, overlap=overlap)


def delete_transcript_index(transcription_id: int) -> bool:
    collection = _collection()
    if collection is None:
        return False

    try:
        collection.delete(where={"transcription_id": int(transcription_id)})
        return True
    except Exception:
        return False


def search_transcript_chunks(
    query: str,
    transcription_id: Optional[int] = None,
    limit: int = 5,
) -> List[dict]:
    collection = _collection()
    if collection is None:
        return []

    normalized_query = _normalize_query_text(query)
    if not normalized_query:
        return []

    try:
        query_embedding = _embed_query(normalized_query)
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": max(1, limit),
            "include": ["documents", "metadatas", "distances"],
        }
        if transcription_id is not None:
            kwargs["where"] = {"transcription_id": int(transcription_id)}
        result = collection.query(**kwargs)
    except Exception:
        return []

    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    ids = (result.get("ids") or [[]])[0]

    hits: list[dict[str, Any]] = []
    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) else {}
        hits.append(
            {
                "id": ids[index] if index < len(ids) else None,
                "text": document,
                "score": distances[index] if index < len(distances) else None,
                "transcription_id": metadata.get("transcription_id"),
                "chunk_index": metadata.get("chunk_index"),
                "source_path": metadata.get("source_path"),
            }
        )

    return hits


def build_semantic_context(
    transcription_id: Optional[int],
    queries: Iterable[str],
    limit_per_query: int = 3,
) -> str:
    ordered_hits: List[dict] = []
    seen: set[str] = set()

    for query in queries:
        normalized_query = _normalize_query_text(query)
        if not normalized_query:
            continue

        for hit in search_transcript_chunks(normalized_query, transcription_id=transcription_id, limit=limit_per_query):
            hit_id = str(hit.get("id") or "")
            if hit_id and hit_id in seen:
                continue
            if hit_id:
                seen.add(hit_id)
            ordered_hits.append(hit)

    if not ordered_hits:
        return "(no semantic transcript context available)"

    return json.dumps(ordered_hits, indent=2, ensure_ascii=False)