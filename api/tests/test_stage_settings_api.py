from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException

from app.llm_actions import LLM_ACTIONS
from app.llm_defaults import OPENAI_IMAGE_SUNBURST_MODEL
from app.mathesys.study_material.images import stage_image_options
from app.models.stage_settings import StageSettingUpdate
from app.models.workspace import WorkspaceResponse
from app.routers.workspaces import (
    delete_stage_setting,
    get_stage_settings,
    put_stage_setting,
)


def _workspace() -> WorkspaceResponse:
    now = datetime.now(UTC)
    return WorkspaceResponse(
        id="ws-1",
        owner_id="owner-1",
        name="Test",
        slug="test",
        description=None,
        status="active",
        created_at=now,
        updated_at=now,
    )


class FakeStageSettingsRepo:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.upserted: list[dict[str, Any]] = []
        self.deleted: list[tuple[str, str]] = []

    async def list_for_workspace(self, workspace_id: str) -> list[dict[str, Any]]:
        return self.rows

    async def upsert(self, **kwargs: Any) -> dict[str, Any]:
        self.upserted.append(kwargs)
        return {
            "workspace_id": kwargs["workspace_id"],
            "stage_action": kwargs["stage_action"],
            "provider": kwargs["provider"],
            "model": kwargs["model"],
            "reasoning_effort": kwargs["reasoning_effort"],
            "reasoning_tokens": kwargs["reasoning_tokens"],
            "voice_id": kwargs.get("voice_id"),
            "image_quality": kwargs.get("image_quality"),
        }

    async def delete(self, *, workspace_id: str, stage_action: str) -> None:
        self.deleted.append((workspace_id, stage_action))


def test_get_returns_one_entry_per_action_with_defaults() -> None:
    repo = FakeStageSettingsRepo()

    response = asyncio.run(get_stage_settings(_workspace(), repo))  # type: ignore[arg-type]

    assert len(response.settings) == len(LLM_ACTIONS) + 2
    narration = next(s for s in response.settings if s.stage_action == "audio_narration")
    assert narration.label == "Audio Narration"
    assert narration.voice_id == narration.default_voice_id
    image = response.settings[-1]
    assert image.stage_action == "study_material_image"
    assert image.label == "Design Image"
    assert image.provider == image.default_provider
    assert image.model == image.default_model
    _, quality = stage_image_options(image.provider, image.model)
    assert image.image_quality == quality
    assert image.default_image_quality == quality
    for setting in response.settings:
        assert setting.is_overridden is False
        assert setting.provider == setting.default_provider
        assert setting.model == setting.default_model


def test_get_reflects_stored_override() -> None:
    repo = FakeStageSettingsRepo(
        rows=[
            {
                "stage_action": "wiki_structuring",
                "provider": "openai",
                "model": "gpt-5.4",
                "reasoning_effort": "high",
                "reasoning_tokens": 2048,
            },
        ],
    )

    response = asyncio.run(get_stage_settings(_workspace(), repo))  # type: ignore[arg-type]

    override = next(s for s in response.settings if s.stage_action == "wiki_structuring")
    assert override.is_overridden is True
    assert override.provider == "openai"
    assert override.model == "gpt-5.4"
    assert override.reasoning_effort == "high"
    assert override.reasoning_tokens == 2048
    assert override.default_provider == "openai"


def test_put_upserts_and_normalizes() -> None:
    repo = FakeStageSettingsRepo()
    payload = StageSettingUpdate(provider="Anthropic", model=" claude-opus-4-8 ")

    result = asyncio.run(
        put_stage_setting("wiki_structuring", payload, _workspace(), repo),  # type: ignore[arg-type]
    )

    assert repo.upserted[0]["provider"] == "anthropic"
    assert repo.upserted[0]["model"] == "claude-opus-4-8"
    assert result.is_overridden is True
    assert result.label


def test_put_unknown_action_404() -> None:
    repo = FakeStageSettingsRepo()
    payload = StageSettingUpdate(provider="openai", model="gpt-4o")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(put_stage_setting("not_a_stage", payload, _workspace(), repo))  # type: ignore[arg-type]

    assert exc.value.status_code == 404


def test_put_invalid_selection_422() -> None:
    repo = FakeStageSettingsRepo()
    # Known model paired with the wrong provider.
    payload = StageSettingUpdate(provider="openai", model="claude-opus-5-5")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(put_stage_setting("wiki_structuring", payload, _workspace(), repo))  # type: ignore[arg-type]

    assert exc.value.status_code == 422
    assert repo.upserted == []


def test_delete_removes_override() -> None:
    repo = FakeStageSettingsRepo()

    asyncio.run(delete_stage_setting("wiki_structuring", _workspace(), repo))  # type: ignore[arg-type]

    assert repo.deleted == [("ws-1", "wiki_structuring")]


def test_delete_unknown_action_404() -> None:
    repo = FakeStageSettingsRepo()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_stage_setting("not_a_stage", _workspace(), repo))  # type: ignore[arg-type]

    assert exc.value.status_code == 404


def test_put_audio_narration_requires_voice() -> None:
    repo = FakeStageSettingsRepo()
    payload = StageSettingUpdate(provider="speechify", model="simba-3.2")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(put_stage_setting("audio_narration", payload, _workspace(), repo))  # type: ignore[arg-type]

    assert exc.value.status_code == 422
    assert repo.upserted == []


def test_put_audio_narration_stores_voice() -> None:
    repo = FakeStageSettingsRepo()
    payload = StageSettingUpdate(
        provider="speechify",
        model="simba-3.2",
        voice_id=" hugh_32 ",
    )

    result = asyncio.run(
        put_stage_setting("audio_narration", payload, _workspace(), repo),  # type: ignore[arg-type]
    )

    assert repo.upserted[0]["provider"] == "speechify"
    assert repo.upserted[0]["model"] == "simba-3.2"
    assert repo.upserted[0]["voice_id"] == "hugh_32"
    assert repo.upserted[0]["reasoning_effort"] is None
    assert result.voice_id == "hugh_32"
    assert result.is_overridden is True


def test_put_design_image_rejects_unknown_model() -> None:
    repo = FakeStageSettingsRepo()
    payload = StageSettingUpdate(provider="openai", model="gpt-image-2")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            put_stage_setting("study_material_image", payload, _workspace(), repo),  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 422
    assert repo.upserted == []


def test_put_design_image_stores_model_without_voice_or_reasoning() -> None:
    repo = FakeStageSettingsRepo()
    payload = StageSettingUpdate(
        provider="Google",
        model=" gemini-nano-banana-2.1 ",
        reasoning_effort="high",
        reasoning_tokens=4096,
        voice_id="should-drop",
    )

    result = asyncio.run(
        put_stage_setting("study_material_image", payload, _workspace(), repo),  # type: ignore[arg-type]
    )

    assert repo.upserted[0]["provider"] == "google"
    assert repo.upserted[0]["model"] == "gemini-nano-banana-2.1"
    assert repo.upserted[0]["reasoning_effort"] is None
    assert repo.upserted[0]["reasoning_tokens"] is None
    assert repo.upserted[0]["voice_id"] is None
    assert result.is_overridden is True
    assert result.model == "gemini-nano-banana-2.1"
    assert repo.upserted[0]["image_quality"] == "medium"
    assert result.image_quality == "medium"
    assert result.voice_id is None


def test_put_design_image_stores_quality() -> None:
    repo = FakeStageSettingsRepo()
    payload = StageSettingUpdate(
        provider="openai",
        model=OPENAI_IMAGE_SUNBURST_MODEL,
        image_quality=" Max ",
    )

    result = asyncio.run(
        put_stage_setting("study_material_image", payload, _workspace(), repo),  # type: ignore[arg-type]
    )

    assert repo.upserted[0]["image_quality"] == "max"
    assert result.image_quality == "max"


def test_put_design_image_rejects_quality_for_the_other_provider() -> None:
    repo = FakeStageSettingsRepo()
    payload = StageSettingUpdate(
        provider="openai",
        model=OPENAI_IMAGE_SUNBURST_MODEL,
        image_quality="minimal",
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            put_stage_setting("study_material_image", payload, _workspace(), repo),  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 422
    assert repo.upserted == []


def test_put_audio_narration_accepts_cartesia() -> None:
    repo = FakeStageSettingsRepo()
    payload = StageSettingUpdate(
        provider="cartesia",
        model="sonic-3.6",
        voice_id="a5136bf9-224c-4d76-b823-52bd5efcffcc",
    )

    result = asyncio.run(
        put_stage_setting("audio_narration", payload, _workspace(), repo),  # type: ignore[arg-type]
    )

    assert repo.upserted[0]["provider"] == "cartesia"
    assert repo.upserted[0]["model"] == "sonic-3.6"
    assert result.voice_id == "a5136bf9-224c-4d76-b823-52bd5efcffcc"
