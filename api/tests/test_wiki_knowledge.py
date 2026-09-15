from __future__ import annotations

from typing import Any

from app.worker.wiki_knowledge_executors import (
    StructureWikiNotesStageExecutor,
    TranscribeWikiNotesStageExecutor,
)


class FakeEmbeddingClient:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(index)] * 3 for index in range(len(texts))]


class FakeWikiWorkerDb:
    def __init__(self, batch: dict[str, Any], *, wiki_rows: list[dict[str, Any]] | None = None) -> None:
        self.batch = batch
        self.wiki_rows: dict[str, dict[str, Any]] = {
            str(row["id"]): dict(row) for row in (wiki_rows or [])
        }
        self.stage_runs: dict[str, dict[str, Any]] = {}
        self.embedding_client = FakeEmbeddingClient()
        self.match_rows: list[dict[str, Any]] = []
        self._stage_n = 1
        self._wiki_n = 1

    def get_wiki_ingest_batch_for_run(
        self,
        production_run_id: str,
        source_id: str | None = None,
    ) -> dict[str, Any] | None:
        if self.batch.get("production_run_id") != production_run_id:
            return None
        if source_id and str(self.batch.get("source_id") or "") != source_id:
            return None
        return self.batch

    def create_stage_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**payload, "id": f"sr-{self._stage_n}"}
        self._stage_n += 1
        self.stage_runs[row["id"]] = row
        return row

    def update_stage_run(self, stage_run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.stage_runs[stage_run_id] = {**self.stage_runs[stage_run_id], **payload}
        return self.stage_runs[stage_run_id]

    def update_wiki_ingest_batch(self, batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.batch["id"] == batch_id
        self.batch = {**self.batch, **payload}
        return self.batch

    def list_wiki_entries_for_workspace(self, workspace_id: str) -> list[dict[str, Any]]:
        return [row for row in self.wiki_rows.values() if row["workspace_id"] == workspace_id]

    def insert_wiki_entries(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        created = []
        for row in rows:
            stored = {**row, "id": f"wiki-{self._wiki_n}"}
            self._wiki_n += 1
            self.wiki_rows[stored["id"]] = stored
            created.append(stored)
        return created

    def update_wiki_entry(self, wiki_entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.wiki_rows[wiki_entry_id] = {**self.wiki_rows[wiki_entry_id], **payload}
        return self.wiki_rows[wiki_entry_id]

    def get_wiki_entries(self, wiki_entry_ids: list[str]) -> list[dict[str, Any]]:
        return [self.wiki_rows[entry_id] for entry_id in wiki_entry_ids if entry_id in self.wiki_rows]

    def match_ndr_segments(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return list(self.match_rows)


class FakeStorage:
    def download(self, path: str, *, bucket: str | None = None) -> bytes:
        return f"content for {path}".encode()


class FakeLLMClient:
    provider = "openai"
    model = "fake-model"

    def __init__(self, content: dict[str, Any]) -> None:
        self.content = content

    def complete_json(self, *, system_prompt: str, user_prompt: str, model=None):
        del system_prompt, user_prompt, model

        class _Result:
            content = self.content
            model = "fake-model"
            provider = "openai"
            token_usage = {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}

        return _Result()


def _batch(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "batch-1",
        "workspace_id": "ws-1",
        "source_id": "src-1",
        "production_run_id": "run-1",
        "title": "Notes",
        "raw_notes": "Enemy system — interdependent parts.\ntempo: rate of ops",
        "chapter": None,
        "status": "transcribed",
        "attachments": [],
        "transcription_error": None,
    }
    row.update(overrides)
    return row


def test_transcribe_skips_when_notes_have_no_attachments() -> None:
    db = FakeWikiWorkerDb(_batch())
    executor = TranscribeWikiNotesStageExecutor(db=db, storage=FakeStorage())  # type: ignore[arg-type]

    stage_run_id = executor.run(production_run_id="run-1", workspace_id="ws-1", source_id="src-1")

    assert db.stage_runs[stage_run_id]["status"] == "completed"
    assert db.stage_runs[stage_run_id]["output"]["skipped"] is True
    assert db.batch["status"] == "transcribed"
    assert db.batch["raw_notes"].startswith("Enemy system")


def test_transcribe_writes_raw_notes_from_attachments(monkeypatch) -> None:
    db = FakeWikiWorkerDb(
        _batch(
            raw_notes="",
            status="transcribing",
            attachments=[
                {"order": 0, "filename": "a.md", "storage_path": "drafts/a.md", "mime_type": "text/markdown"},
            ],
        ),
    )
    monkeypatch.setattr(
        "app.worker.wiki_knowledge_executors.transcribe_attachments_in_order",
        lambda items: "transcribed notes",
    )
    executor = TranscribeWikiNotesStageExecutor(db=db, storage=FakeStorage())  # type: ignore[arg-type]

    stage_run_id = executor.run(production_run_id="run-1", workspace_id="ws-1", source_id="src-1")

    assert db.batch["raw_notes"] == "transcribed notes"
    assert db.batch["status"] == "transcribed"
    assert db.stage_runs[stage_run_id]["output"]["skipped"] is False


def test_transcribe_markdown_attachment_passthrough() -> None:
    db = FakeWikiWorkerDb(
        _batch(
            raw_notes="",
            status="transcribing",
            attachments=[
                {
                    "order": 0,
                    "filename": "notes.md",
                    "storage_path": "ocs-prep/notes.md",
                    "mime_type": "text/markdown",
                },
            ],
        ),
    )

    class MarkdownStorage:
        def download(self, path: str, *, bucket: str | None = None) -> bytes:
            del path, bucket
            return b"# Enemy system\n\nInterdependent parts."

    executor = TranscribeWikiNotesStageExecutor(db=db, storage=MarkdownStorage())  # type: ignore[arg-type]
    stage_run_id = executor.run(production_run_id="run-1", workspace_id="ws-1", source_id="src-1")

    assert "Enemy system" in db.batch["raw_notes"]
    assert "Interdependent parts" in db.batch["raw_notes"]
    assert db.batch["status"] == "transcribed"
    assert db.stage_runs[stage_run_id]["output"]["skipped"] is False


def test_structure_promotes_canonical_entries(monkeypatch) -> None:
    db = FakeWikiWorkerDb(_batch())
    db.match_rows = [
        {
            "id": "seg-1",
            "source_id": "src-1",
            "sequence_index": 42,
            "text": "The enemy is a system.",
            "locator": {"page": 87},
            "similarity": 0.8,
        },
    ]
    monkeypatch.setattr(
        "app.worker.wiki_knowledge_executors.get_llm_client",
        lambda _action: FakeLLMClient(
            {
                "entries": [
                    {
                        "label": "Enemy System",
                        "entry_kind": "concept",
                        "definition": "The enemy as a system of interdependent parts.",
                        "aliases": [],
                        "pronunciation": None,
                        "importance": "essential",
                        "prerequisite_labels": [],
                        "note_excerpt": "Enemy system — interdependent parts.",
                    },
                ],
                "unparsed_fragments": [],
            },
        ),
    )
    executor = StructureWikiNotesStageExecutor(db=db)  # type: ignore[arg-type]

    stage_run_id = executor.run(production_run_id="run-1", workspace_id="ws-1", source_id="src-1")

    rows = list(db.wiki_rows.values())
    assert len(rows) == 1
    entry = rows[0]
    assert entry["status"] == "canonical"
    assert entry["preferred_label"] == "Enemy System"
    assert entry["origin"]["kind"] == "wiki_ingest"
    assert entry["origin"]["production_run_id"] == "run-1"
    assert entry["origin"]["stage_run_id"] == stage_run_id
    assert entry["evidence"][0]["segment_id"] == "seg-1"
    assert db.batch["status"] == "committed"
    assert db.stage_runs[stage_run_id]["status"] == "completed"


def test_structure_failure_marks_batch_and_stage_failed(monkeypatch) -> None:
    db = FakeWikiWorkerDb(_batch(raw_notes=""))
    executor = StructureWikiNotesStageExecutor(db=db)  # type: ignore[arg-type]

    try:
        executor.run(production_run_id="run-1", workspace_id="ws-1", source_id="src-1")
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "empty" in str(exc).lower()

    assert db.batch["status"] == "failed"
    failed = next(row for row in db.stage_runs.values() if row["status"] == "failed")
    assert failed["stage_id"] == "structure-wiki-notes"
    assert db.wiki_rows == {}


def test_transcribe_missing_batch_for_source_fails() -> None:
    db = FakeWikiWorkerDb(_batch(source_id="src-1"))
    executor = TranscribeWikiNotesStageExecutor(db=db, storage=FakeStorage())  # type: ignore[arg-type]

    try:
        executor.run(production_run_id="run-1", workspace_id="ws-1", source_id="src-other")
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "src-other" in str(exc)
