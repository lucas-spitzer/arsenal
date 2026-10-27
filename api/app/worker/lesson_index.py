"""Index Academy ELO lesson files and ELOs into lesson_chunks for Discussions."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from app.services.embeddings import EmbeddingClient, to_pgvector_literal
from app.services.lesson_files import skip_reason
from app.services.lesson_text import (
    LessonTextError,
    chunk_sections,
    extract_sections,
    objective_chunk_text,
)

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 64
MAX_ERROR_CHARS = 500


class LessonIndexStore(Protocol):
    embedding_client: EmbeddingClient

    def get_lesson(self, lesson_id: str) -> dict[str, Any] | None: ...
    def list_lesson_objectives(self, lesson_id: str) -> list[dict[str, Any]]: ...
    def get_lesson_resource(self, resource_id: str) -> dict[str, Any] | None: ...
    def update_lesson_resource(self, resource_id: str, payload: dict[str, Any]) -> None: ...
    def delete_lesson_chunks_for_resource(self, resource_id: str) -> None: ...
    def delete_lesson_objective_chunks(self, lesson_id: str) -> None: ...
    def insert_lesson_chunks(self, rows: list[dict[str, Any]]) -> None: ...


class LessonFileStore(Protocol):
    def download(self, path: str, *, bucket: str | None = None) -> bytes: ...


def _embed(client: EmbeddingClient, texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        vectors.extend(client.embed(texts[start : start + EMBED_BATCH_SIZE]))
    if len(vectors) != len(texts):
        raise RuntimeError("Embedding response did not match the number of chunks.")
    return vectors


class LessonIndexer:
    def __init__(self, db: LessonIndexStore, storage: LessonFileStore, *, bucket: str) -> None:
        self.db = db
        self.storage = storage
        self.bucket = bucket

    def index_resource(self, resource_id: str) -> dict[str, Any]:
        resource = self.db.get_lesson_resource(resource_id)
        if not resource or resource.get("kind") != "file":
            return {"resource_id": resource_id, "status": "missing"}
        lesson = self.db.get_lesson(str(resource["lesson_id"]))
        if not lesson:
            return {"resource_id": resource_id, "status": "missing"}

        filename = str(resource.get("filename") or resource.get("label") or "file")
        reason = skip_reason(filename)
        if reason:
            self.db.delete_lesson_chunks_for_resource(resource_id)
            return self._finish(resource_id, "skipped", reason)

        self.db.update_lesson_resource(resource_id, {"index_status": "indexing", "index_error": None})
        try:
            content = self.storage.download(str(resource["storage_path"]), bucket=self.bucket)
            sections = extract_sections(filename, content)
        except LessonTextError as exc:
            return self._finish(resource_id, "failed", str(exc))
        except Exception as exc:  # noqa: BLE001 - storage errors vary
            logger.exception("Lesson file %s could not be read.", resource_id)
            return self._finish(resource_id, "failed", f"Could not read the file: {exc}")

        header = f"{lesson['title']} · {resource.get('label') or filename}"
        chunks = chunk_sections(sections, header=header)
        if not chunks:
            self.db.delete_lesson_chunks_for_resource(resource_id)
            return self._finish(resource_id, "failed", "No readable text found (scanned or image-only file).")

        try:
            vectors = _embed(self.db.embedding_client, [chunk.text for chunk in chunks])
        except Exception as exc:  # noqa: BLE001 - provider errors vary
            logger.exception("Embedding failed for lesson file %s.", resource_id)
            return self._finish(resource_id, "failed", f"Embedding failed: {exc}")

        rows = [
            {
                "workspace_id": resource["workspace_id"],
                "lesson_id": resource["lesson_id"],
                "resource_id": resource_id,
                "kind": "file_text",
                "sequence_index": chunk.sequence_index,
                "text": chunk.text,
                "locator": chunk.locator,
                "embedding": to_pgvector_literal(vector),
            }
            for chunk, vector in zip(chunks, vectors)
        ]
        self.db.delete_lesson_chunks_for_resource(resource_id)
        self.db.insert_lesson_chunks(rows)
        result = self._finish(resource_id, "ready", None)
        result["chunks"] = len(rows)
        return result

    def index_objectives(self, lesson_id: str) -> dict[str, Any]:
        lesson = self.db.get_lesson(lesson_id)
        if not lesson:
            return {"lesson_id": lesson_id, "status": "missing"}
        objectives = self.db.list_lesson_objectives(lesson_id)
        texts = [objective_chunk_text(str(lesson["title"]), objective) for objective in objectives]
        vectors = _embed(self.db.embedding_client, texts) if texts else []
        rows = [
            {
                "workspace_id": lesson["workspace_id"],
                "lesson_id": lesson_id,
                "objective_id": objective["id"],
                "kind": "objective",
                "sequence_index": int(objective["position"]),
                "text": text,
                "locator": {"position": int(objective["position"]), "code": objective.get("code")},
                "embedding": to_pgvector_literal(vector),
            }
            for objective, text, vector in zip(objectives, texts, vectors)
        ]
        self.db.delete_lesson_objective_chunks(lesson_id)
        self.db.insert_lesson_chunks(rows)
        return {"lesson_id": lesson_id, "status": "ready", "chunks": len(rows)}

    def _finish(self, resource_id: str, status: str, error: str | None) -> dict[str, Any]:
        self.db.update_lesson_resource(
            resource_id,
            {"index_status": status, "index_error": error[:MAX_ERROR_CHARS] if error else None},
        )
        return {"resource_id": resource_id, "status": status}
