"""Tests for the generate-narration stage's alignment and pipeline wiring."""

import base64
import hashlib
import json
from typing import Any

import pytest

from app.intellex.structuring.chunk import display_markdown, flatten_markdown
from app.pipeline import SUPPORTED_TARGET_ARTIFACTS, build_pipeline
from app.services.elevenlabs_client import (
    ElevenLabsClient,
    model_supports_stitching,
    words_from_alignment,
)


def test_narration_audio_is_a_supported_target() -> None:
    assert "narration_audio" in SUPPORTED_TARGET_ARTIFACTS


def test_build_pipeline_appends_generate_narration_step() -> None:
    pipeline = build_pipeline(["narration_audio"])
    assert [step["step"] for step in pipeline][-1] == "generate-narration"


def test_words_from_alignment_groups_on_whitespace() -> None:
    text = "Hi there, world."
    characters = list(text)
    starts = [i * 0.1 for i in range(len(characters))]
    ends = [i * 0.1 + 0.1 for i in range(len(characters))]

    words = words_from_alignment(characters, starts, ends)

    assert [w.word for w in words] == text.split()
    assert words[0].index == 0
    assert words[0].start == 0.0
    # "Hi" ends when its last character ('i', index 1) ends.
    assert words[0].end == starts[1] + 0.1
    # Word count parity with the Reader's tokenization of the plain text.
    assert len(words) == len(text.split())


def test_words_from_alignment_handles_empty() -> None:
    assert words_from_alignment([], [], []) == []


def test_progress_output_summary_is_fraction() -> None:
    from app.worker.narration_executor import _progress_output

    output = _progress_output(
        done=2,
        total=280,
        narrated=2,
        reused=0,
        skipped=0,
        character_count=209,
        voice_id="voice-1",
        model_id="eleven_v3",
    )

    assert output["summary"] == "2/280 clips"
    assert output["segments_done"] == 2
    assert output["segments_total"] == 280
    assert output["segments_narrated"] == 2


def test_display_markdown_keeps_emphasis_and_word_parity() -> None:
    md = "The  *testing* effect is **real**."
    display = display_markdown(md)

    assert display == "The *testing* effect is **real**."
    assert len(display.split()) == len(flatten_markdown(md).split())


def test_display_markdown_none_when_plain() -> None:
    assert display_markdown("No emphasis here.") is None
    # Sup tags are stripped from both copies, so the md adds nothing.
    assert display_markdown("Footnote<sup>1</sup> text.") is None


# --- Request-stitching model support ----------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)
        self.headers: dict[str, str] = {}

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeHttpClient:
    """Captures request bodies; yields queued responses in order."""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = responses
        self.bodies: list[dict[str, Any]] = []

    def post(self, url: str, *, params: Any, headers: Any, json: dict[str, Any]) -> _FakeResponse:
        self.bodies.append(dict(json))
        return self.responses[min(len(self.bodies) - 1, len(self.responses) - 1)]


def _ok_response() -> _FakeResponse:
    text = "Hello world"
    characters = list(text)
    return _FakeResponse(
        200,
        {
            "audio_base64": base64.b64encode(b"mp3").decode(),
            "alignment": {
                "characters": characters,
                "character_start_times_seconds": [i * 0.1 for i in range(len(characters))],
                "character_end_times_seconds": [i * 0.1 + 0.1 for i in range(len(characters))],
            },
        },
    )


def test_model_supports_stitching_flags_v3() -> None:
    assert not model_supports_stitching("eleven_v3")
    assert not model_supports_stitching("eleven_v3_preview")
    assert model_supports_stitching("eleven_multilingual_v2")
    assert model_supports_stitching("eleven_flash_v2_5")


def test_v3_requests_omit_stitching_hints() -> None:
    client = ElevenLabsClient(api_key="k", voice_id="v", model_id="eleven_v3")
    fake = _FakeHttpClient([_ok_response()])

    result = client.synthesize_with_timestamps(
        "Hello world",
        previous_request_ids=["r1"],
        next_text="Next paragraph.",
        client=fake,  # type: ignore[arg-type]
    )

    assert len(fake.bodies) == 1
    body = fake.bodies[0]
    assert "previous_request_ids" not in body
    assert "previous_text" not in body
    assert "next_text" not in body
    assert [w.word for w in result.words] == ["Hello", "world"]


def test_unsupported_model_rejection_strips_hints_and_retries() -> None:
    # A model we believe supports stitching gets rejected anyway: the client
    # must strip the hints and immediately retry instead of failing the run.
    rejection = _FakeResponse(
        400,
        text=json.dumps(
            {
                "detail": {
                    "type": "validation_error",
                    "code": "unsupported_model",
                    "message": "Providing previous_text or next_text is not yet supported",
                }
            }
        ),
    )
    client = ElevenLabsClient(api_key="k", voice_id="v", model_id="eleven_multilingual_v2")
    fake = _FakeHttpClient([rejection, _ok_response()])

    result = client.synthesize_with_timestamps(
        "Hello world",
        previous_request_ids=["r1"],
        next_text="Next paragraph.",
        client=fake,  # type: ignore[arg-type]
    )

    assert len(fake.bodies) == 2
    assert "previous_request_ids" in fake.bodies[0]
    assert "next_text" in fake.bodies[0]
    assert "previous_request_ids" not in fake.bodies[1]
    assert "next_text" not in fake.bodies[1]
    assert [w.word for w in result.words] == ["Hello", "world"]


# --- Narration artifact JSON manifest ----------------------------------------


class _FakeWorkerDb:
    def __init__(self, narration_rows: list[dict[str, Any]]) -> None:
        self.narration_rows = narration_rows
        self.created_artifacts: list[dict[str, Any]] = []
        self.updated_artifacts: list[tuple[str, dict[str, Any]]] = []
        self.updated_stage_runs: list[tuple[str, dict[str, Any]]] = []
        self.chapters: list[dict[str, Any]] = []
        self.ndr_segments: list[dict[str, Any]] = []

    def create_stage_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {**payload, "id": "sr-1"}

    def update_stage_run(self, stage_run_id: str, payload: dict[str, Any]):
        self.updated_stage_runs.append((stage_run_id, payload))
        return payload

    def list_narration_segments_for_source(
        self,
        source_id: str,
        voice_id: str,
        model_id: str | None = None,
    ):
        return self.narration_rows

    def list_document_chapters_for_source(self, source_id: str):
        return self.chapters

    def list_ndr_segments_for_source(self, source_id: str):
        return self.ndr_segments

    def insert_narration_segment(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.upsert_narration_segment(payload)

    def upsert_narration_segment(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.narration_rows.append(payload)
        return payload

    def create_artifact(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created_artifacts.append(payload)
        return {**payload, "id": "art-1"}

    def update_artifact(self, artifact_id: str, payload: dict[str, Any]):
        self.updated_artifacts.append((artifact_id, payload))
        return payload


class _FakeWorkerStorage:
    sources_bucket = "sources"

    def __init__(self) -> None:
        self.uploads: dict[str, bytes] = {}
        self.upload_content_types: dict[str, str] = {}
        self.upload_buckets: dict[str, str] = {}

    def upload(
        self,
        path: str,
        content: bytes,
        *,
        bucket: str | None = None,
        content_type: str = "application/octet-stream",
    ) -> None:
        self.uploads[path] = content
        self.upload_content_types[path] = content_type
        self.upload_buckets[path] = bucket or self.sources_bucket


def test_publish_artifact_writes_json_manifest() -> None:
    from app.worker.narration_executor import NarrationStageExecutor

    rows = [
        {
            "segment_id": "seg-a",
            "audio_path": "workspaces/ws-1/sources/src-1/narration/v/seg-a.mp3",
            "duration_seconds": 2.5,
            "character_count": 40,
            "words": [{"i": 0, "w": "Hello", "s": 0.0, "e": 0.5}],
        },
        {
            "segment_id": "seg-b",
            "audio_path": "workspaces/ws-1/sources/src-1/narration/v/seg-b.mp3",
            "duration_seconds": 3.0,
            "character_count": 50,
            "words": [{"i": 0, "w": "World", "s": 0.0, "e": 0.6}],
        },
    ]
    db = _FakeWorkerDb(rows)
    storage = _FakeWorkerStorage()
    client = ElevenLabsClient(api_key="k", voice_id="voice-1", model_id="eleven_v3")
    executor = NarrationStageExecutor(
        db=db, storage=storage, client=client, max_segment_chars=9500  # type: ignore[arg-type]
    )

    chapters = [
        {
            "id": "ch-1",
            "title": "Chapter One",
            "sequence_index": 0,
            "segment_ids": ["seg-h", "seg-a", "seg-b"],
        }
    ]
    segments = {
        "seg-a": {"sequence_index": 1},
        "seg-b": {"sequence_index": 2},
    }

    source_storage = "ocs-prep/src-1/warfighting.pdf"
    file_info = executor._publish_artifact(
        workspace_id="ws-1",
        production_run_id="run-1",
        stage_run_id="sr-1",
        source={
            "id": "src-1",
            "slug": "src-1",
            "workspace_slug": "ocs-prep",
            "filename": "warfighting.pdf",
            "storage_path": source_storage,
            "source_metadata": {},
        },
        chapters=chapters,
        segments=segments,
    )

    assert file_info is not None
    assert file_info["artifact_id"] == "art-1"
    assert file_info["filename"] == "narration.json"
    assert file_info["storage_path"] == "ocs-prep/src-1/narration.json"
    assert storage.upload_buckets[file_info["storage_path"]] == "sources"

    created = db.created_artifacts[0]
    assert created["artifact_type"] == "narration_audio"
    assert created["format"] == "json"
    assert created["manifest"]["segment_count"] == 2
    assert created["manifest"]["chapter_titles"] == ["Chapter One"]

    body = storage.uploads[file_info["storage_path"]]
    assert storage.upload_content_types[file_info["storage_path"]] == "application/json"
    manifest = json.loads(body.decode("utf-8"))
    assert manifest["voice_id"] == "voice-1"
    assert manifest["total_duration_seconds"] == 5.5
    assert manifest["segment_count"] == 2
    first = manifest["chapters"][0]["segments"][0]
    assert first["segment_id"] == "seg-a"
    assert first["audio_path"] == "workspaces/ws-1/sources/src-1/narration/v/seg-a.mp3"
    assert first["words"][0]["w"] == "Hello"
    assert "file" not in first


def test_publish_artifact_none_when_no_narration() -> None:
    from app.worker.narration_executor import NarrationStageExecutor

    executor = NarrationStageExecutor(
        db=_FakeWorkerDb([]),  # type: ignore[arg-type]
        storage=_FakeWorkerStorage(),  # type: ignore[arg-type]
        client=ElevenLabsClient(api_key="k", voice_id="v", model_id="eleven_v3"),
        max_segment_chars=9500,
    )
    assert (
        executor._publish_artifact(
            workspace_id="ws-1",
            production_run_id="run-1",
            stage_run_id="sr-1",
            source={"id": "src-1", "filename": "x.pdf", "source_metadata": {}},
            chapters=[],
            segments={},
        )
        is None
    )


def test_failed_run_still_publishes_artifact() -> None:
    from app.services.elevenlabs_client import ElevenLabsError
    from app.worker.narration_executor import NarrationStageExecutor

    rows = [
        {
            "segment_id": "seg-a",
            "audio_path": "workspaces/ws-1/sources/src-1/narration/v/seg-a.mp3",
            "duration_seconds": 2.5,
            "character_count": 40,
            "words": [{"i": 0, "w": "Hello", "s": 0.0, "e": 0.5}],
        }
    ]
    db = _FakeWorkerDb(rows)
    db.chapters = [
        {
            "id": "ch-1",
            "title": "Chapter One",
            "sequence_index": 0,
            "segment_ids": ["seg-a"],
        }
    ]
    db.ndr_segments = [{"id": "seg-a", "sequence_index": 1}]
    executor = NarrationStageExecutor(
        db=db,  # type: ignore[arg-type]
        storage=_FakeWorkerStorage(),  # type: ignore[arg-type]
        client=ElevenLabsClient(api_key="k", voice_id="voice-1", model_id="eleven_v3"),
        max_segment_chars=9500,
    )

    def _fail(**kwargs: Any) -> tuple[dict[str, Any], int, dict[str, Any]]:
        raise ElevenLabsError("quota_exceeded")

    executor._narrate_source = _fail  # type: ignore[method-assign]

    with pytest.raises(ElevenLabsError, match="quota_exceeded"):
        executor.run_for_source(
            production_run_id="run-1",
            workspace_id="ws-1",
            source={
                "id": "src-1",
                "slug": "src-1",
                "workspace_slug": "ocs-prep",
                "filename": "warfighting.pdf",
                "storage_path": "ocs-prep/src-1/warfighting.pdf",
                "source_metadata": {},
            },
        )

    assert db.created_artifacts[0]["artifact_type"] == "narration_audio"
    fail_update = db.updated_stage_runs[-1][1]
    assert fail_update["status"] == "failed"
    assert fail_update["promoted"]["artifact_ids"] == ["art-1"]


def test_pack_chapter_clips_fits_and_splits() -> None:
    from app.worker.narration_executor import pack_chapter_clips

    short = [
        {"id": "a", "text": "aaaa"},
        {"id": "b", "text": "bbbb"},
    ]
    clips, oversize, empty = pack_chapter_clips(short, max_chars=20)
    assert len(clips) == 1
    assert [row["id"] for row in clips[0]] == ["a", "b"]
    assert oversize == []
    assert empty == 0

    split = [
        {"id": "a", "text": "aaaaaaaaaa"},
        {"id": "b", "text": "bbbbbbbbbb"},
    ]
    clips, oversize, empty = pack_chapter_clips(split, max_chars=20)
    assert [[row["id"] for row in clip] for clip in clips] == [["a"], ["b"]]
    assert oversize == []

    mixed = [
        {"id": "empty", "text": "  "},
        {"id": "huge", "text": "x" * 30},
        {"id": "ok", "text": "hello"},
    ]
    clips, oversize, empty = pack_chapter_clips(mixed, max_chars=20)
    assert empty == 1
    assert [row["id"] for row in oversize] == ["huge"]
    assert [[row["id"] for row in clip] for clip in clips] == [["ok"]]


def test_pack_chapter_clips_skips_punctuation_only() -> None:
    from app.worker.narration_executor import pack_chapter_clips

    rows = [
        {"id": "dot", "text": "."},
        {"id": "ok", "text": "Hello"},
    ]
    clips, oversize, empty = pack_chapter_clips(rows, max_chars=20)
    assert empty == 1
    assert oversize == []
    assert [[row["id"] for row in clip] for clip in clips] == [["ok"]]


def test_assign_words_to_paragraphs_keeps_clip_timeline() -> None:
    from app.services.elevenlabs_client import WordTiming
    from app.worker.narration_executor import assign_words_to_paragraphs

    paragraphs = [
        {"id": "a", "text": "Hello world"},
        {"id": "b", "text": "Go now"},
    ]
    words = [
        WordTiming(0, "Hello", 0.0, 0.2, 0, 5),
        WordTiming(1, "world", 0.2, 0.4, 6, 11),
        WordTiming(2, "Go", 0.5, 0.6, 13, 15),
        WordTiming(3, "now", 0.6, 0.8, 16, 19),
    ]
    assigned = assign_words_to_paragraphs(paragraphs, words)
    assert [w.word for w in assigned[0]] == ["Hello", "world"]
    assert assigned[0][0].index == 0
    assert assigned[1][0].word == "Go"
    assert assigned[1][0].index == 0
    assert assigned[1][0].start == 0.5


def test_assign_words_to_paragraphs_rejects_missing_source_span() -> None:
    from app.services.elevenlabs_client import WordTiming
    from app.worker.narration_executor import assign_words_to_paragraphs

    with pytest.raises(ValueError, match="missing source character spans"):
        assign_words_to_paragraphs(
            [{"id": "a", "text": "Hello world"}],
            [WordTiming(0, "Hello", 0.0, 0.2)],
        )


class _FakeTts:
    provider = "speechify"
    voice_id = "voice-1"
    model_id = "simba-3.2"
    max_segment_chars = 200
    enabled = True

    def __init__(self) -> None:
        self.texts: list[str] = []

    def synthesize_with_timestamps(self, text: str, **kwargs: Any) -> Any:
        from app.services.elevenlabs_client import NarrationResult, WordTiming
        from app.services.tts.alignment import tokenize_with_spans

        self.texts.append(text)
        words = []
        t = 0.0
        for token in tokenize_with_spans(text):
            words.append(
                WordTiming(
                    token.index,
                    token.text,
                    t,
                    t + 0.1,
                    token.start_char,
                    token.end_char,
                )
            )
            t += 0.1
        return NarrationResult(
            audio=b"mp3",
            words=words,
            duration_seconds=t,
            request_id="req-1",
            character_cost=len(text),
        )


def test_narrate_source_writes_one_clip_per_chapter() -> None:
    from app.worker.narration_executor import NarrationStageExecutor

    db = _FakeWorkerDb([])
    db.chapters = [
        {
            "id": "ch-1",
            "title": "One",
            "sequence_index": 0,
            "segment_ids": ["h1", "p1", "p2"],
        }
    ]
    db.ndr_segments = [
        {"id": "h1", "kind": "heading", "text": "One"},
        {"id": "p1", "kind": "paragraph", "text": "Hello there."},
        {"id": "p2", "kind": "paragraph", "text": "More words here."},
    ]
    storage = _FakeWorkerStorage()
    client = _FakeTts()
    executor = NarrationStageExecutor(
        db=db,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
        max_segment_chars=200,
    )
    output, chars, _ctx = executor._narrate_source(
        workspace_id="ws-1",
        source={
            "id": "src-1",
            "slug": "src-1",
            "workspace_slug": "ocs-prep",
            "storage_path": "ocs-prep/src-1/file.pdf",
        },
        stage_run_id="sr-1",
    )
    assert len(client.texts) == 1
    assert "Hello there." in client.texts[0]
    assert "More words here." in client.texts[0]
    paths = list(storage.uploads)
    assert len(paths) == 1
    assert paths[0].endswith("ch-1-00.mp3")
    assert len(db.narration_rows) == 2
    assert db.narration_rows[0]["audio_path"] == db.narration_rows[1]["audio_path"] == paths[0]
    assert db.narration_rows[0]["provider"] == "speechify"
    assert db.narration_rows[0]["model_id"] == "simba-3.2"
    assert db.narration_rows[0]["alignment_source"] == "provider"
    assert db.narration_rows[0]["alignment_quality"]["valid"] is True
    assert db.narration_rows[0]["text_hash"] == hashlib.sha256(
        b"Hello there."
    ).hexdigest()
    assert output["segments_narrated"] == 1
    assert output["segments_total"] == 1
    assert output["summary"] == "1/1 clips"
    assert chars == len(client.texts[0])


def test_narrate_source_splits_chapter_over_cap() -> None:
    from app.worker.narration_executor import NarrationStageExecutor

    db = _FakeWorkerDb([])
    db.chapters = [
        {
            "id": "ch-1",
            "title": "One",
            "sequence_index": 0,
            "segment_ids": ["p1", "p2"],
        }
    ]
    db.ndr_segments = [
        {"id": "p1", "kind": "paragraph", "text": "aaaaaaaaaa"},
        {"id": "p2", "kind": "paragraph", "text": "bbbbbbbbbb"},
    ]
    storage = _FakeWorkerStorage()
    client = _FakeTts()
    executor = NarrationStageExecutor(
        db=db,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
        max_segment_chars=20,
    )
    output, _chars, _ctx = executor._narrate_source(
        workspace_id="ws-1",
        source={
            "id": "src-1",
            "slug": "src-1",
            "workspace_slug": "ocs-prep",
            "storage_path": "ocs-prep/src-1/file.pdf",
        },
        stage_run_id="sr-1",
    )
    assert client.texts == ["aaaaaaaaaa", "bbbbbbbbbb"]
    paths = sorted(storage.uploads)
    assert paths[0].endswith("ch-1-00.mp3")
    assert paths[1].endswith("ch-1-01.mp3")
    assert output["segments_narrated"] == 2
    assert output["segments_total"] == 2


def test_narrate_source_reuses_matching_chapter_clip() -> None:
    from app.worker.narration_executor import NarrationStageExecutor

    audio_path = (
        "ocs-prep/src-1/audio/speechify/simba-3-2/voice-1/ch-1-00.mp3"
    )
    db = _FakeWorkerDb(
        [
            {
                "segment_id": "p1",
                "audio_path": audio_path,
                "model_id": "simba-3.2",
                "text_hash": hashlib.sha256(b"Hello there.").hexdigest(),
            },
            {
                "segment_id": "p2",
                "audio_path": audio_path,
                "model_id": "simba-3.2",
                "text_hash": hashlib.sha256(b"More words here.").hexdigest(),
            },
        ]
    )
    db.chapters = [
        {
            "id": "ch-1",
            "title": "One",
            "sequence_index": 0,
            "segment_ids": ["p1", "p2"],
        }
    ]
    db.ndr_segments = [
        {"id": "p1", "kind": "paragraph", "text": "Hello there."},
        {"id": "p2", "kind": "paragraph", "text": "More words here."},
    ]
    client = _FakeTts()
    executor = NarrationStageExecutor(
        db=db,  # type: ignore[arg-type]
        storage=_FakeWorkerStorage(),  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
        max_segment_chars=200,
    )
    output, chars, _ctx = executor._narrate_source(
        workspace_id="ws-1",
        source={
            "id": "src-1",
            "slug": "src-1",
            "workspace_slug": "ocs-prep",
            "storage_path": "ocs-prep/src-1/file.pdf",
        },
        stage_run_id="sr-1",
    )
    assert client.texts == []
    assert chars == 0
    assert output["segments_reused"] == 1
    assert output["segments_narrated"] == 0


def test_narrate_source_skips_mid_run_gemini_invalid_argument() -> None:
    from app.services.gemini_tts_client import GeminiTtsError
    from app.worker.narration_executor import NarrationStageExecutor

    class _FlakyGemini(_FakeTts):
        provider = "google"
        model_id = "gemini-3.1-flash-tts-preview"
        audio_content_type = "audio/wav"

        def synthesize_with_timestamps(self, text: str, **kwargs: Any) -> Any:
            if text.startswith("b"):
                raise GeminiTtsError(
                    "Gemini TTS synthesis failed (10 chars): 400 INVALID_ARGUMENT. "
                    "{'error': {'code': 400, 'message': 'Request contains an "
                    "invalid argument.', 'status': 'INVALID_ARGUMENT'}}"
                )
            return super().synthesize_with_timestamps(text, **kwargs)

    db = _FakeWorkerDb([])
    db.chapters = [
        {
            "id": "ch-1",
            "title": "One",
            "sequence_index": 0,
            "segment_ids": ["p1", "p2"],
        }
    ]
    db.ndr_segments = [
        {"id": "p1", "kind": "paragraph", "text": "aaaaaaaaaa"},
        {"id": "p2", "kind": "paragraph", "text": "bbbbbbbbbb"},
    ]
    storage = _FakeWorkerStorage()
    client = _FlakyGemini()
    executor = NarrationStageExecutor(
        db=db,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
        max_segment_chars=20,
    )
    output, chars, _ctx = executor._narrate_source(
        workspace_id="ws-1",
        source={
            "id": "src-1",
            "slug": "src-1",
            "workspace_slug": "ocs-prep",
            "storage_path": "ocs-prep/src-1/file.pdf",
        },
        stage_run_id="sr-1",
    )
    assert client.texts == ["aaaaaaaaaa"]
    assert output["segments_narrated"] == 1
    assert output["segments_skipped"] == 1
    assert output["segments_total"] == 2
    assert len(db.narration_rows) == 1
    assert chars == 10


def test_narrate_source_fails_first_gemini_invalid_argument() -> None:
    from app.services.gemini_tts_client import GeminiTtsError
    from app.worker.narration_executor import NarrationStageExecutor

    class _BrokenGemini(_FakeTts):
        provider = "google"
        model_id = "gemini-3.1-flash-tts-preview"

        def synthesize_with_timestamps(self, text: str, **kwargs: Any) -> Any:
            raise GeminiTtsError(
                "Gemini TTS synthesis failed (12 chars): 400 INVALID_ARGUMENT. "
                "{'error': {'code': 400, 'message': 'Request contains an "
                "invalid argument.', 'status': 'INVALID_ARGUMENT'}}"
            )

    db = _FakeWorkerDb([])
    db.chapters = [
        {
            "id": "ch-1",
            "title": "One",
            "sequence_index": 0,
            "segment_ids": ["p1"],
        }
    ]
    db.ndr_segments = [
        {"id": "p1", "kind": "paragraph", "text": "Hello there."},
    ]
    executor = NarrationStageExecutor(
        db=db,  # type: ignore[arg-type]
        storage=_FakeWorkerStorage(),  # type: ignore[arg-type]
        client=_BrokenGemini(),  # type: ignore[arg-type]
        max_segment_chars=200,
    )
    with pytest.raises(GeminiTtsError, match="INVALID_ARGUMENT"):
        executor._narrate_source(
            workspace_id="ws-1",
            source={
                "id": "src-1",
                "slug": "src-1",
                "workspace_slug": "ocs-prep",
                "storage_path": "ocs-prep/src-1/file.pdf",
            },
            stage_run_id="sr-1",
        )

