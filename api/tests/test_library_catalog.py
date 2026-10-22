import asyncio
from types import SimpleNamespace
from typing import Any

from app.repositories.wiki_entries import WIKI_ENTRY_LIST_COLUMNS, WikiEntryRepository
from app.routers.assessments import _with_signed_visuals, load_library_catalog, router

NOW = "2026-01-01T00:00:00Z"


def test_library_route_is_registered() -> None:
    paths = {getattr(route, "path", "") for route in router.routes}
    assert "/workspaces/{workspace_id}/library" in paths


def test_wiki_list_omits_embeddings() -> None:
    assert "embedding" not in WIKI_ENTRY_LIST_COLUMNS
    assert "embedded_at" not in WIKI_ENTRY_LIST_COLUMNS
    assert "definition" in WIKI_ENTRY_LIST_COLUMNS

    class Database:
        columns = ""

        async def select_many(self, table: str, **kwargs: Any) -> list[dict[str, Any]]:
            assert table == "wiki_entries"
            self.columns = str(kwargs["columns"])
            return []

    database = Database()
    asyncio.run(WikiEntryRepository(database).list_for_workspace("ws-1"))  # type: ignore[arg-type]
    assert database.columns.split(",") == list(WIKI_ENTRY_LIST_COLUMNS)


def test_visuals_are_signed_together() -> None:
    in_flight = 0
    peak = 0

    class Storage:
        async def create_signed_url(self, *, bucket: str, path: str, expires_in: int) -> str:
            nonlocal in_flight, peak
            assert bucket == "sources"
            assert expires_in == 3600
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0)
            in_flight -= 1
            return f"https://files.example/{path}"

    rows = [
        {"id": "a", "visual": {"storage_path": "visuals/one.png", "kind": "diagram"}},
        {"id": "b", "visual": {"storage_path": "visuals/one.png", "kind": "diagram"}},
        {"id": "c", "visual": {"storage_path": "visuals/two.png", "kind": "icon"}},
        {"id": "d", "visual": None},
    ]
    settings = SimpleNamespace(sources_bucket="sources", signed_url_expires_seconds=3600)
    signed = asyncio.run(_with_signed_visuals(rows, Storage(), settings))  # type: ignore[arg-type]

    assert peak == 2
    assert signed[0]["visual"]["url"] == "https://files.example/visuals/one.png"
    assert signed[1]["visual"]["url"] == signed[0]["visual"]["url"]
    assert signed[2]["visual"]["url"] == "https://files.example/visuals/two.png"
    assert signed[3]["visual"] is None


def test_library_catalog_loads_every_list_once() -> None:
    calls: list[str] = []

    class Sources:
        async def list_for_workspace(self, workspace_id: str, owner_id: str) -> list[dict[str, Any]]:
            calls.append(f"sources:{workspace_id}:{owner_id}")
            return [
                {
                    "id": "source-1",
                    "workspace_id": "ws-1",
                    "owner_id": "owner-1",
                    "filename": "book.pdf",
                    "slug": "book",
                    "mime_type": "application/pdf",
                    "storage_path": "sources/book.pdf",
                    "file_hash": "abc",
                    "file_size_bytes": 10,
                    "source_metadata": {},
                    "status": "ready",
                    "source_kind": "document",
                    "created_at": NOW,
                    "updated_at": NOW,
                }
            ]

    class Artifacts:
        async def list_for_workspace(self, workspace_id: str, **_: Any) -> list[dict[str, Any]]:
            calls.append(f"artifacts:{workspace_id}")
            return [
                {
                    "id": "art-1",
                    "workspace_id": "ws-1",
                    "source_id": "source-1",
                    "production_run_id": None,
                    "artifact_type": "electronic_book",
                    "format": "epub",
                    "filename": "book.epub",
                    "storage_path": "artifacts/book.epub",
                    "file_size_bytes": 20,
                    "manifest": {},
                    "origin": {},
                    "created_at": NOW,
                }
            ]

    class Wiki:
        async def list_for_workspace(self, workspace_id: str, **_: Any) -> list[dict[str, Any]]:
            calls.append(f"wiki:{workspace_id}")
            return [
                {
                    "id": "wiki-1",
                    "workspace_id": "ws-1",
                    "preferred_label": "Fire team",
                    "canonical_slug": "fire-team",
                    "definition": "Four Marines.",
                    "significance": None,
                    "category": None,
                    "items": [],
                    "pronunciation": None,
                    "aliases": [],
                    "prerequisites": [],
                    "importance": "essential",
                    "entry_kind": "term",
                    "status": "canonical",
                    "evidence": [],
                    "origin": {},
                    "created_at": NOW,
                    "updated_at": NOW,
                }
            ]

    class Assessments:
        async def list_flashcards(self, workspace_id: str, **_: Any) -> list[dict[str, Any]]:
            calls.append(f"flashcards:{workspace_id}")
            return [
                {
                    "id": "card-1",
                    "workspace_id": "ws-1",
                    "source_id": "source-1",
                    "production_run_id": None,
                    "stage_run_id": None,
                    "front": "What is a fire team?",
                    "back": "Four Marines.",
                    "difficulty": "easy",
                    "tags": [],
                    "citations": [],
                    "origin": {},
                    "visual": {
                        "kind": "diagram",
                        "placement": "back",
                        "alt": "Hill",
                        "storage_path": "visuals/hill.png",
                        "mime_type": "image/png",
                        "filename": "hill.png",
                    },
                    "created_at": NOW,
                }
            ]

        async def list_quizzes(self, workspace_id: str, **_: Any) -> list[dict[str, Any]]:
            calls.append(f"quizzes:{workspace_id}")
            return []

        async def list_scenarios(self, workspace_id: str, **_: Any) -> list[dict[str, Any]]:
            calls.append(f"scenarios:{workspace_id}")
            return []

    class Projects:
        async def list_titles(self, workspace_id: str) -> list[dict[str, Any]]:
            calls.append(f"titles:{workspace_id}")
            return [{"id": "proj-1", "source_id": "source-1", "title": "Offense"}]

    class Storage:
        async def create_signed_url(self, *, bucket: str, path: str, expires_in: int) -> str:
            return f"https://files.example/{path}?exp={expires_in}&bucket={bucket}"

    settings = SimpleNamespace(sources_bucket="sources", signed_url_expires_seconds=3600)
    catalog = asyncio.run(
        load_library_catalog(
            workspace_id="ws-1",
            owner_id="owner-1",
            sources=Sources(),  # type: ignore[arg-type]
            artifacts=Artifacts(),  # type: ignore[arg-type]
            wiki_entries=Wiki(),  # type: ignore[arg-type]
            assessments=Assessments(),  # type: ignore[arg-type]
            projects=Projects(),  # type: ignore[arg-type]
            storage=Storage(),  # type: ignore[arg-type]
            settings=settings,  # type: ignore[arg-type]
        )
    )

    assert calls == [
        "sources:ws-1:owner-1",
        "artifacts:ws-1",
        "wiki:ws-1",
        "flashcards:ws-1",
        "quizzes:ws-1",
        "scenarios:ws-1",
        "titles:ws-1",
    ]
    assert catalog.sources[0].filename == "book.pdf"
    assert catalog.wiki_entries[0].preferred_label == "Fire team"
    assert catalog.flashcards[0].visual is not None
    assert catalog.flashcards[0].visual.url == "https://files.example/visuals/hill.png?exp=3600&bucket=sources"
    assert catalog.knowledge_titles[0].title == "Offense"
