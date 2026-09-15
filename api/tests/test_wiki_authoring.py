from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.models.wiki_ingest import WikiIngestCreate
from app.services.production_runs import ProductionRunEnqueueError
from app.services.wiki_authoring import WikiAuthoringError, WikiAuthoringService, WikiIngestNotFoundError


class FakeWikiEntryRepository:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows: dict[str, dict[str, Any]] = {
            str(row["id"]): row for row in (rows or [])
        }
        self._next_id = 1

    async def list_for_workspace(self, workspace_id: str, **_kwargs) -> list[dict[str, Any]]:
        return [row for row in self.rows.values() if row["workspace_id"] == workspace_id]

    async def get_for_workspace(self, wiki_entry_id: str, workspace_id: str):
        row = self.rows.get(wiki_entry_id)
        return row if row and row["workspace_id"] == workspace_id else None

    async def get_many(self, wiki_entry_ids: list[str]) -> list[dict[str, Any]]:
        return [self.rows[entry_id] for entry_id in wiki_entry_ids if entry_id in self.rows]

    async def insert_many(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        created = []
        for row in rows:
            row = {**row, "id": f"wiki-{self._next_id}"}
            self._next_id += 1
            self.rows[row["id"]] = row
            created.append(row)
        return created

    async def update(self, wiki_entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.rows[wiki_entry_id] = {**self.rows[wiki_entry_id], **payload}
        return self.rows[wiki_entry_id]


class _FakeBatchDb:
    async def select_one(self, table: str, *, filters: dict[str, str], columns: str = "*"):
        del table, filters, columns
        return {"id": "ws-1", "slug": "ocs-prep"}


class FakeBatchRepository:
    def __init__(self, chapters: list[dict[str, Any]] | None = None) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.chapters = chapters or []
        self._next_id = 1
        self.db = _FakeBatchDb()

    async def list_for_workspace(self, workspace_id: str, **_kwargs) -> list[dict[str, Any]]:
        return [row for row in self.rows.values() if row["workspace_id"] == workspace_id]

    async def get_for_workspace(self, batch_id: str, workspace_id: str):
        row = self.rows.get(batch_id)
        return row if row and row["workspace_id"] == workspace_id else None

    async def insert(self, payload: dict[str, Any]) -> dict[str, Any]:
        row_id = str(payload.get("id") or f"batch-{self._next_id}")
        if "id" not in payload:
            self._next_id += 1
        row = {**payload, "id": row_id}
        self.rows[row["id"]] = row
        return row

    async def update(self, batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.rows[batch_id] = {**self.rows[batch_id], **payload}
        return self.rows[batch_id]

    async def list_chapters_for_source(self, source_id: str) -> list[dict[str, Any]]:
        del source_id
        return self.chapters


class FakeProductionRunRepository:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self._next_id = 1

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**payload, "id": f"run-{self._next_id}"}
        self._next_id += 1
        self.rows[row["id"]] = row
        return row

    async def update(self, production_run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.rows[production_run_id] = {**self.rows[production_run_id], **payload}
        return self.rows[production_run_id]


class FakeEmbeddingClient:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(index)] * 3 for index in range(len(texts))]


class FakeLLMClient:
    provider = "openai"
    model = "fake-model"

    def __init__(self, content: dict[str, Any]) -> None:
        self.content = content
        self.calls: list[dict[str, str]] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str, model=None):
        self.calls.append({"system": system_prompt, "user": user_prompt})
        del model

        class _Result:
            content = self.content
            model = "fake-model"
            provider = "openai"
            token_usage = {"input_tokens": 8, "output_tokens": 12, "total_tokens": 20}

        return _Result()


class FakeStorage:
    def __init__(self) -> None:
        self.uploads: list[dict[str, Any]] = []

    async def upload(
        self,
        *,
        bucket: str,
        path: str,
        content: bytes,
        content_type: str,
        upsert: bool = False,
    ):
        del upsert
        self.uploads.append(
            {
                "bucket": bucket,
                "path": path,
                "content": content,
                "content_type": content_type,
            },
        )
        return {}


def _existing_wiki_row(
    slug: str,
    label: str,
    definition: str,
    *,
    workspace_id: str = "ws-1",
) -> dict[str, Any]:
    return {
        "id": f"wiki-existing-{slug}",
        "workspace_id": workspace_id,
        "canonical_slug": slug,
        "preferred_label": label,
        "definition": definition,
        "entry_kind": "concept",
        "importance": "supporting",
        "aliases": [],
        "prerequisites": [],
        "status": "canonical",
        "evidence": [],
        "origin": {"kind": "wiki_ingest", "note_excerpt": "tempo: rate of ops"},
    }


def _service(
    *,
    wiki_rows: list[dict[str, Any]] | None = None,
    chapters: list[dict[str, Any]] | None = None,
    storage: Any | None = None,
    revise_llm_client: FakeLLMClient | None = None,
) -> WikiAuthoringService:
    return WikiAuthoringService(
        wiki_entries=FakeWikiEntryRepository(wiki_rows),  # type: ignore[arg-type]
        batches=FakeBatchRepository(chapters),  # type: ignore[arg-type]
        production_runs=FakeProductionRunRepository(),  # type: ignore[arg-type]
        embedding_client=FakeEmbeddingClient(),
        revise_llm_client=revise_llm_client,
        storage=storage,
    )


def test_create_batch_queues_production_run_without_structuring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(
        chapters=[
            {
                "id": "ch-3",
                "title": "The Enemy as a System",
                "sequence_index": 3,
                "segment_ids": ["seg-1"],
                "sections": [],
            },
        ],
    )
    enqueued: list[str] = []
    monkeypatch.setattr(
        "app.services.wiki_authoring.enqueue_production_run",
        lambda _settings, run_id: enqueued.append(run_id) or "job-1",
    )

    batch = asyncio.run(
        service.create_batch(
            WikiIngestCreate(
                notes="Enemy system…\ntempo: rate of ops",
                source_id="src-1",
                chapter_hint="3",
            ),
            "ws-1",
            owner_id="user-1",
        ),
    )

    assert batch["status"] == "transcribed"
    assert batch["raw_notes"].startswith("Enemy system")
    assert batch["entries"] == []
    assert batch["chapter"]["chapter_id"] == "ch-3"
    assert batch["production_run_id"] == "run-1"
    assert enqueued == ["run-1"]
    run = service.production_runs.rows["run-1"]
    assert run["target_artifacts"] == ["wiki_knowledge"]
    assert run["source_ids"] == ["src-1"]
    assert run["status"] == "queued"
    steps = [step["step"] for step in run["pipeline"]]
    assert "transcribe-wiki-notes" in steps
    assert "structure-wiki-notes" in steps


def test_create_batch_requires_source_id() -> None:
    with pytest.raises(Exception):
        WikiIngestCreate(notes="notes", source_id="")


def test_create_batch_rejects_oversized_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service()
    monkeypatch.setattr(
        "app.services.wiki_authoring.enqueue_production_run",
        lambda *_args, **_kwargs: "job-1",
    )
    huge_notes = "x" * (service.settings.wiki_authoring.max_notes_chars + 1)

    with pytest.raises(WikiAuthoringError, match="exceed"):
        asyncio.run(
            service.create_batch(
                WikiIngestCreate(notes=huge_notes, source_id="src-1"),
                "ws-1",
                owner_id="user-1",
            ),
        )


def test_create_batch_enqueue_failure_marks_run_and_batch_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    monkeypatch.setattr(
        "app.services.wiki_authoring.enqueue_production_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("redis down")),
    )

    with pytest.raises(ProductionRunEnqueueError):
        asyncio.run(
            service.create_batch(
                WikiIngestCreate(notes="notes", source_id="src-1"),
                "ws-1",
                owner_id="user-1",
            ),
        )

    run = next(iter(service.production_runs.rows.values()))
    batch = next(iter(service.batches.rows.values()))
    assert run["status"] == "failed"
    assert batch["status"] == "failed"


def test_create_file_batch_stores_attachments_and_queues_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = FakeStorage()
    service = _service(storage=storage)
    enqueued: list[str] = []
    monkeypatch.setattr(
        "app.services.wiki_authoring.enqueue_production_run",
        lambda _settings, run_id: enqueued.append(run_id) or "job-1",
    )

    batch = asyncio.run(
        service.create_file_batch(
            workspace_id="ws-1",
            owner_id="user-1",
            source_id="src-1",
            chapter_hint="3",
            title="Ch. 3 photos",
            files=[
                ("page1.md", "text/markdown", b"Enemy system"),
                ("page2.txt", "text/plain", b"insight: tempo wins"),
            ],
        ),
    )

    assert batch["status"] == "transcribing"
    assert batch["raw_notes"] == ""
    assert batch["production_run_id"] == "run-1"
    assert len(batch["attachments"]) == 2
    assert len(storage.uploads) == 2
    assert enqueued == ["run-1"]


def test_create_file_batch_requires_source_id() -> None:
    service = _service(storage=FakeStorage())

    with pytest.raises(WikiAuthoringError, match="source_id is required"):
        asyncio.run(
            service.create_file_batch(
                workspace_id="ws-1",
                owner_id="user-1",
                source_id="",
                chapter_hint=None,
                title=None,
                files=[("notes.md", "text/markdown", b"term: def")],
            ),
        )


def test_create_file_batch_does_not_require_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = FakeStorage()
    service = _service(storage=storage)
    monkeypatch.setattr(
        "app.services.wiki_authoring.enqueue_production_run",
        lambda *_args, **_kwargs: "job-1",
    )

    batch = asyncio.run(
        service.create_file_batch(
            workspace_id="ws-1",
            owner_id="user-1",
            source_id="src-1",
            chapter_hint=None,
            title=None,
            files=[("notes.md", "text/markdown", b"term: def")],
        ),
    )

    assert batch["status"] == "transcribing"
    assert batch["production_run_id"]


def test_create_entry_quick_add_inserts_and_embeds() -> None:
    service = _service()

    row = asyncio.run(
        service.create_entry(
            "ws-1",
            preferred_label="OODA Loop",
            definition="Observe, orient, decide, act.",
            entry_kind="concept",
            importance="essential",
            aliases=["Boyd cycle"],
            pronunciation=None,
        ),
    )

    assert row["canonical_slug"] == "ooda-loop"
    assert row["origin"] == {"kind": "manual"}
    stored = asyncio.run(service.wiki_entries.get_for_workspace(row["id"], "ws-1"))
    assert stored["embedding"]


def test_create_entry_accepts_reader_define_origin() -> None:
    service = _service()

    row = asyncio.run(
        service.create_entry(
            "ws-1",
            preferred_label="Tempo",
            definition="The pace of decisions in a fight.",
            entry_kind="term",
            importance="supporting",
            aliases=[],
            pronunciation=None,
            origin={
                "kind": "reader_define",
                "mode": "contextual",
                "source_id": "src-1",
                "term": "Tempo",
            },
        ),
    )

    assert row["origin"]["kind"] == "reader_define"
    assert row["status"] == "canonical"


def test_create_entry_rejects_duplicate_slug() -> None:
    service = _service(
        wiki_rows=[_existing_wiki_row("ooda-loop", "OODA Loop", "def")],
    )

    with pytest.raises(WikiAuthoringError, match="already exists"):
        asyncio.run(
            service.create_entry(
                "ws-1",
                preferred_label="OODA Loop",
                definition="def",
                entry_kind="concept",
                importance="supporting",
                aliases=[],
                pronunciation=None,
            ),
        )


def test_deprecate_entry_sets_status() -> None:
    service = _service(
        wiki_rows=[_existing_wiki_row("tempo", "Tempo", "def")],
    )

    row = asyncio.run(service.deprecate_entry("wiki-existing-tempo", "ws-1"))

    assert row["status"] == "deprecated"


def test_revise_returns_proposal_without_writing() -> None:
    original = _existing_wiki_row("tempo", "Tempo", "The rate of operations.")
    service = _service(
        wiki_rows=[original],
        revise_llm_client=FakeLLMClient(
            {
                "definition": "The pace of decisions relative to the enemy.",
                "preferred_label": "Tempo",
                "aliases": ["operational tempo"],
            },
        ),
    )

    proposal = asyncio.run(
        service.revise_entry("wiki-existing-tempo", "ws-1", "Tighten this for a flashcard."),
    )

    assert proposal["definition"] == "The pace of decisions relative to the enemy."
    assert proposal["aliases"] == ["operational tempo"]
    stored = asyncio.run(service.wiki_entries.get_for_workspace("wiki-existing-tempo", "ws-1"))
    assert stored["definition"] == "The rate of operations."


def test_update_entry_writes_after_revise() -> None:
    service = _service(
        wiki_rows=[_existing_wiki_row("tempo", "Tempo", "The rate of operations.")],
    )

    updated = asyncio.run(
        service.update_entry(
            "wiki-existing-tempo",
            "ws-1",
            {"definition": "The pace of decisions relative to the enemy."},
        ),
    )

    assert updated["definition"] == "The pace of decisions relative to the enemy."
    assert updated["embedding"]


def test_revise_missing_entry_is_not_found() -> None:
    service = _service()

    with pytest.raises(WikiIngestNotFoundError):
        asyncio.run(service.revise_entry("missing", "ws-1", "rewrite"))
