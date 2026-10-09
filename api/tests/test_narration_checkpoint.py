from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.narration_checkpoint import clear_narration_checkpoints
from app.services.production_runs import create_and_enqueue_production_run
from tests.test_production_runs import FakeProductionRunRepository


class FakeNarrationSegments:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    async def list_all_for_voice(
        self,
        source_id: str,
        workspace_id: str,
        owner_id: str,
        *,
        model_id: str,
        voice_id: str,
    ) -> list[dict[str, Any]]:
        del workspace_id, owner_id
        return [
            row
            for row in self.rows
            if row["source_id"] == source_id
            and row["model_id"] == model_id
            and row["voice_id"] == voice_id
        ]

    async def delete_for_voice(
        self,
        source_id: str,
        workspace_id: str,
        owner_id: str,
        *,
        model_id: str,
        voice_id: str,
    ) -> None:
        del workspace_id, owner_id
        self.rows = [
            row
            for row in self.rows
            if not (
                row["source_id"] == source_id
                and row["model_id"] == model_id
                and row["voice_id"] == voice_id
            )
        ]


class FakeArtifacts:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    async def list_narration_for_source(
        self,
        source_id: str,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        del workspace_id
        return [
            row
            for row in self.rows
            if row["source_id"] == source_id and row["artifact_type"] == "narration_audio"
        ]

    async def delete(self, artifact_id: str) -> None:
        self.rows = [row for row in self.rows if row["id"] != artifact_id]


class FakeStorage:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, list[str]]] = []

    async def delete_paths(self, *, bucket: str, paths: list[str]) -> None:
        self.deleted.append((bucket, paths))


class FakeStageSettings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    async def list_for_workspace(self, workspace_id: str) -> list[dict[str, Any]]:
        del workspace_id
        return self.rows


def _settings() -> Any:
    return SimpleNamespace(
        sources_bucket="sources",
        narration=SimpleNamespace(model_id="eleven_v3", voice_id="OtherVoice"),
    )


def test_clear_narration_checkpoint_keeps_other_voices() -> None:
    segments = FakeNarrationSegments(
        [
            {
                "source_id": "src-1",
                "model_id": "gemini-3.8-flash-tts",
                "voice_id": "Sadaltager",
                "audio_path": "audio/kept-voice.wav",
            },
            {
                "source_id": "src-1",
                "model_id": "gemini-3.8-flash-tts",
                "voice_id": "Kore",
                "audio_path": "audio/other-voice.wav",
            },
        ]
    )
    artifacts = FakeArtifacts(
        [
            {
                "id": "art-1",
                "source_id": "src-1",
                "artifact_type": "narration_audio",
                "storage_path": "src-1/narration.json",
                "manifest": {
                    "voice_id": "Sadaltager",
                    "model_id": "gemini-3.8-flash-tts",
                },
            },
            {
                "id": "art-2",
                "source_id": "src-1",
                "artifact_type": "narration_audio",
                "storage_path": "src-1/other.json",
                "manifest": {"voice_id": "Kore", "model_id": "gemini-3.8-flash-tts"},
            },
        ]
    )
    storage = FakeStorage()

    asyncio.run(
        clear_narration_checkpoints(
            workspace_id="ws-1",
            owner_id="user-1",
            source_ids=["src-1"],
            model_id="gemini-3.8-flash-tts",
            voice_id="Sadaltager",
            narration_segments=segments,  # type: ignore[arg-type]
            artifacts=artifacts,  # type: ignore[arg-type]
            storage=storage,  # type: ignore[arg-type]
            bucket="sources",
        )
    )

    assert [(row["voice_id"], row["audio_path"]) for row in segments.rows] == [
        ("Kore", "audio/other-voice.wav")
    ]
    assert [row["id"] for row in artifacts.rows] == ["art-2"]
    assert storage.deleted == [
        ("sources", ["audio/kept-voice.wav", "src-1/narration.json"])
    ]


def test_restart_deletes_configured_voice_and_ignores_other_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    segments = FakeNarrationSegments(
        [
            {
                "source_id": "src-1",
                "model_id": "gemini-3.8-flash-tts",
                "voice_id": "Sadaltager",
                "audio_path": "audio/src-1.wav",
            },
            {
                "source_id": "src-2",
                "model_id": "gemini-3.8-flash-tts",
                "voice_id": "Sadaltager",
                "audio_path": "audio/src-2.wav",
            },
            {
                "source_id": "src-1",
                "model_id": "eleven_v3",
                "voice_id": "OtherVoice",
                "audio_path": "audio/other-model.mp3",
            },
        ]
    )
    artifacts = FakeArtifacts([])
    storage = FakeStorage()
    runs = FakeProductionRunRepository()
    enqueued: list[str] = []
    monkeypatch.setattr(
        "app.services.production_runs.enqueue_production_run",
        lambda _settings, run_id: enqueued.append(run_id) or "job-1",
    )

    asyncio.run(
        create_and_enqueue_production_run(
            workspace_id="ws-1",
            owner_id="user-1",
            source_ids=["src-1"],
            target_artifacts=["narration_audio"],
            settings=_settings(),
            production_runs=runs,  # type: ignore[arg-type]
            narration_restart_source_ids=["src-1", "src-2"],
            stage_settings=FakeStageSettings(  # type: ignore[arg-type]
                [
                    {
                        "stage_action": "audio_narration",
                        "provider": "google",
                        "model": "gemini-3.8-flash-tts",
                        "voice_id": "Sadaltager",
                    }
                ]
            ),
            narration_segments=segments,  # type: ignore[arg-type]
            artifacts=artifacts,  # type: ignore[arg-type]
            storage=storage,  # type: ignore[arg-type]
        )
    )

    assert [(row["source_id"], row["voice_id"]) for row in segments.rows] == [
        ("src-2", "Sadaltager"),
        ("src-1", "OtherVoice"),
    ]
    assert storage.deleted == [("sources", ["audio/src-1.wav"])]
    assert enqueued == ["run-1"]


def test_restart_ids_are_ignored_when_narration_is_not_a_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    segments = FakeNarrationSegments(
        [
            {
                "source_id": "src-1",
                "model_id": "gemini-3.8-flash-tts",
                "voice_id": "Sadaltager",
                "audio_path": "audio/src-1.wav",
            }
        ]
    )
    monkeypatch.setattr(
        "app.services.production_runs.enqueue_production_run",
        lambda *_args, **_kwargs: "job-1",
    )

    asyncio.run(
        create_and_enqueue_production_run(
            workspace_id="ws-1",
            owner_id="user-1",
            source_ids=["src-1"],
            target_artifacts=["electronic_book"],
            settings=object(),  # type: ignore[arg-type]
            production_runs=FakeProductionRunRepository(),  # type: ignore[arg-type]
            narration_restart_source_ids=["src-1"],
            narration_segments=segments,  # type: ignore[arg-type]
        )
    )

    assert len(segments.rows) == 1
