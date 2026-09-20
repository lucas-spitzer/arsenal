from __future__ import annotations

import base64
from typing import Any

import pytest

from app.services.api_pricing import (
    cost_elevenlabs_usage,
    cost_speechify_usage,
    cost_tts_usage,
)
from app.services.cartesia_client import CartesiaClient
from app.services.elevenlabs_client import force_align_audio
from app.services.gemini_tts_client import GeminiTtsClient
from app.services.speechify_client import SpeechifyClient, words_from_speech_marks
from app.services.tts.audio import even_word_timings, pcm_s16le_to_wav
from app.services.tts.catalog import TTS_MODEL_CATALOG, get_tts_catalog_model
from app.services.tts.factory import (
    get_tts_client,
    narration_override_from_rows,
    reset_narration_override,
    set_narration_override,
)
from app.tts_defaults import tts_provider_for_model


def test_tts_provider_for_model() -> None:
    assert tts_provider_for_model("simba-3.2") == "speechify"
    assert tts_provider_for_model("simba-3.0") == "speechify"
    assert tts_provider_for_model("eleven_v3") == "elevenlabs"
    assert tts_provider_for_model("eleven_multilingual_v2") == "elevenlabs"
    assert tts_provider_for_model("sonic-3.6") == "cartesia"
    assert tts_provider_for_model("gemini-3.1-flash-tts-preview") == "google"


def test_tts_catalog_ships_simba_eleven_sonic_and_gemini() -> None:
    models = {entry.model for entry in TTS_MODEL_CATALOG}
    assert models == {
        "simba-3.2",
        "eleven_v3",
        "sonic-3.6",
        "gemini-3.1-flash-tts-preview",
    }
    simba = get_tts_catalog_model("simba-3.2")
    eleven = get_tts_catalog_model("eleven_v3")
    sonic = get_tts_catalog_model("sonic-3.6")
    gemini = get_tts_catalog_model("gemini-3.1-flash-tts-preview")
    assert simba is not None and simba.price_per_million == 10.0
    assert simba.capability_tier == 1
    assert eleven is not None and eleven.price_per_million == 100.0
    assert eleven.capability_tier == 5
    assert eleven.default_voice_id == "4YYIPFl9wE5c4L2eu2Gb"
    assert eleven.voices[0].display_name == "Burt Reynolds"
    assert sonic is not None and sonic.price_per_million == 50.0
    assert sonic.capability_tier == 4
    assert sonic.provider == "cartesia"
    assert [voice.display_name for voice in sonic.voices] == ["Carson", "Jameson"]
    assert gemini is not None and gemini.price_per_million == 40.0
    assert gemini.capability_tier == 3
    assert gemini.provider == "google"
    assert [voice.display_name for voice in gemini.voices] == ["Kore", "Sadaltager"]
    assert get_tts_catalog_model("simba-3.0") is None
    assert get_tts_catalog_model("eleven_multilingual_v2") is None


def test_tts_list_prices_per_million_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPEECHIFY_PRICE_PER_CHARACTER", raising=False)
    monkeypatch.delenv("ELEVENLABS_PRICE_PER_CHARACTER", raising=False)
    monkeypatch.delenv("CARTESIA_PRICE_PER_CHARACTER", raising=False)
    monkeypatch.delenv("GOOGLE_TTS_PRICE_PER_CHARACTER", raising=False)

    speechify = cost_speechify_usage(model="simba-3.2", character_count=1_000_000)
    eleven = cost_elevenlabs_usage(model="eleven_v3", character_count=1_000_000)
    cartesia = cost_tts_usage(
        provider="cartesia",
        model="sonic-3.6",
        character_count=1_000_000,
    )
    gemini = cost_tts_usage(
        provider="google",
        model="gemini-3.1-flash-tts-preview",
        character_count=1_000_000,
    )

    assert speechify["cost_usd"] == 10.0
    assert eleven["cost_usd"] == 100.0
    assert cartesia["cost_usd"] == 50.0
    assert gemini["cost_usd"] == 40.0


def test_words_from_speech_marks_converts_ms_to_seconds() -> None:
    text = "Hello, welcome to Speechify"
    marks = {
        "chunks": [
            {"start": 0, "end": 6, "start_time": 125, "end_time": 375, "value": "Hello,"},
            {"start": 7, "end": 14, "start_time": 375, "end_time": 750, "value": "welcome"},
            {"start": 15, "end": 17, "start_time": 750, "end_time": 875, "value": "to"},
            {"start": 18, "end": 27, "start_time": 875, "end_time": 1850, "value": "Speechify"},
        ],
    }

    words = words_from_speech_marks(marks, text)

    assert [word.word for word in words] == ["Hello,", "welcome", "to", "Speechify"]
    assert words[0].start == 0.125
    assert words[0].end == 0.375
    assert words[-1].end == 1.85
    assert words[0].index == 0


def test_words_from_speech_marks_accepts_flat_list() -> None:
    words = words_from_speech_marks(
        [{"value": "Hello", "start_time": 0, "end_time": 400}],
        "Hello",
    )
    assert len(words) == 1
    assert words[0].end == 0.4


def test_speechify_character_offsets_absorb_punctuation_marks() -> None:
    words = words_from_speech_marks(
        [
            {"value": "“", "start": 0, "end": 1, "start_time": 0, "end_time": 40},
            {"value": "In", "start": 1, "end": 3, "start_time": 40, "end_time": 220},
            {
                "value": "tactics,”",
                "start": 4,
                "end": 12,
                "start_time": 220,
                "end_time": 800,
            },
        ],
        "“In tactics,”",
        duration_seconds=0.8,
    )

    assert [word.word for word in words] == ["“In", "tactics,”"]
    assert words[0].start == 0
    assert words[1].end == 0.8
    assert [(word.start_char, word.end_char) for word in words] == [(0, 3), (4, 13)]


def test_speechify_multiword_mark_maps_across_source_tokens() -> None:
    words = words_from_speech_marks(
        [
            {
                "value": "A. M. Gray",
                "start": 0,
                "end": 10,
                "start_time": 200,
                "end_time": 1200,
            },
        ],
        "A. M. Gray",
        duration_seconds=1.2,
    )

    assert [word.word for word in words] == ["A.", "M.", "Gray"]
    assert words[0].start == 0.2
    assert words[0].end < words[1].end < words[2].end


def test_get_tts_client_routes_by_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEECHIFY_API_KEY", "sf-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-key")
    monkeypatch.setenv("CARTESIA_API_KEY", "car-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    from app.config import get_settings

    get_settings.cache_clear()

    speechify = get_tts_client(model="simba-3.2", voice_id="hugh_32")
    eleven = get_tts_client(model="eleven_v3", voice_id="voice-1")
    cartesia = get_tts_client(
        model="sonic-3.6",
        voice_id="4df027cb-2920-4a1f-8c34-f21529d5c3fe",
    )
    gemini = get_tts_client(model="gemini-3.1-flash-tts-preview", voice_id="Kore")

    assert speechify.provider == "speechify"
    assert speechify.voice_id == "hugh_32"
    assert eleven.provider == "elevenlabs"
    assert eleven.model_id == "eleven_v3"
    assert cartesia.provider == "cartesia"
    assert cartesia.model_id == "sonic-3.6"
    assert gemini.provider == "google"
    assert gemini.voice_id == "Kore"

    get_settings.cache_clear()


def test_narration_override_from_rows() -> None:
    override = narration_override_from_rows(
        [
            {"stage_action": "wiki_structuring", "provider": "openai", "model": "gpt-5.4"},
            {
                "stage_action": "audio_narration",
                "provider": "speechify",
                "model": "simba-3.2",
                "voice_id": "beatrice_32",
            },
        ],
    )
    assert override is not None
    assert override.voice_id == "beatrice_32"
    token = set_narration_override(override)
    try:
        client = get_tts_client()
        assert client.provider == "speechify"
        assert client.voice_id == "beatrice_32"
    finally:
        reset_narration_override(token)


def test_speechify_batch_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEECHIFY_API_KEY", "sf-key")
    from app.config import get_settings

    get_settings.cache_clear()

    class _FakeResponse:
        status_code = 200
        headers: dict[str, str] = {}
        text = ""

        def json(self) -> dict[str, Any]:
            return {
                "audio_data": base64.b64encode(b"mp3").decode(),
                "billable_characters_count": 5,
                "speech_marks": {
                    "end_time": 800,
                    "chunks": [
                        {"value": "Hello", "start_time": 0, "end_time": 400},
                        {"value": "world", "start_time": 400, "end_time": 800},
                    ],
                },
            }

    class _FakeHttp:
        def post(self, url: str, *, headers: Any, json: dict[str, Any]) -> _FakeResponse:
            assert "speech" in url
            assert json["model"] == "simba-3.2"
            assert json["voice_id"] == "hugh_32"
            return _FakeResponse()

    client = SpeechifyClient(api_key="k", voice_id="hugh_32", model_id="simba-3.2")
    result = client.synthesize_with_timestamps("Hello world", client=_FakeHttp())  # type: ignore[arg-type]

    assert result.audio == b"mp3"
    assert [word.word for word in result.words] == ["Hello", "world"]
    assert result.duration_seconds == 0.8
    assert result.character_cost == 5

    get_settings.cache_clear()


def test_even_word_timings_spreads_tokens() -> None:
    words = even_word_timings("Hello world", 1.0)
    assert [word.word for word in words] == ["Hello", "world"]
    assert words[0].start == 0.0
    assert words[0].end == 0.5
    assert words[1].start == 0.5
    assert words[1].end == 1.0


def test_forced_alignment_maps_finished_audio_to_source_words() -> None:
    class _Response:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {
                "words": [
                    {"text": "Hello", "start": 0.1, "end": 0.4, "loss": 0.01},
                    {"text": "world", "start": 0.5, "end": 0.9, "loss": 0.02},
                ],
                "loss": 0.015,
            }

    class _Http:
        def post(self, url: str, **kwargs: Any) -> _Response:
            assert url.endswith("/forced-alignment")
            assert kwargs["data"]["text"] == "Hello world"
            assert kwargs["files"]["file"][1] == b"audio"
            return _Response()

    words, quality = force_align_audio(
        audio=b"audio",
        text="Hello world",
        api_key="key",
        content_type="audio/mpeg",
        client=_Http(),  # type: ignore[arg-type]
    )

    assert [word.word for word in words] == ["Hello", "world"]
    assert words[0].start == 0.1
    assert words[-1].end == 0.9
    assert quality["valid"] is True
    assert quality["loss"] == 0.015


def test_pcm_s16le_to_wav_writes_riff_header() -> None:
    wav = pcm_s16le_to_wav(b"\x00\x00" * 8, sample_rate=24000)
    assert wav.startswith(b"RIFF")
    assert b"WAVE" in wav[:16]


def test_cartesia_sse_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARTESIA_API_KEY", "car-key")
    from app.config import get_settings

    get_settings.cache_clear()

    pcm = b"\x00\x00" * 44100
    chunk = base64.b64encode(pcm).decode()
    lines = [
        f'data: {{"type":"chunk","done":false,"status_code":206,"step_time":1,"data":"{chunk}"}}',
        "",
        (
            "data: "
            '{"type":"timestamps","done":false,"status_code":206,'
            '"word_timestamps":{"words":["Hello"],'
            '"start":[0],"end":[0.4]}}'
        ),
        "",
        (
            "data: "
            '{"type":"timestamps","done":false,"status_code":206,'
            '"word_timestamps":{"words":["world"],'
            '"start":[0.5],"end":[1.0]}}'
        ),
        "",
        'data: {"type":"done","done":true,"status_code":206}',
        "",
    ]

    class _FakeStreamResponse:
        status_code = 200
        headers = {"request-id": "cart-1"}

        def iter_lines(self) -> Any:
            yield from lines

        def __enter__(self) -> "_FakeStreamResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class _FakeHttp:
        def stream(self, method: str, url: str, *, headers: Any, json: dict[str, Any]) -> _FakeStreamResponse:
            assert method == "POST"
            assert url.endswith("/tts/sse")
            assert json["model_id"] == "sonic-3.6"
            assert json["add_timestamps"] is True
            assert json["use_normalized_timestamps"] is False
            assert json["locale"] == "en-US"
            assert json["voice"]["id"] == "4df027cb-2920-4a1f-8c34-f21529d5c3fe"
            return _FakeStreamResponse()

    client = CartesiaClient(
        api_key="k",
        voice_id="4df027cb-2920-4a1f-8c34-f21529d5c3fe",
        model_id="sonic-3.6",
    )
    result = client.synthesize_with_timestamps("Hello world", client=_FakeHttp())  # type: ignore[arg-type]

    assert result.audio.startswith(b"RIFF")
    assert [word.word for word in result.words] == ["Hello", "world"]
    assert result.words[0].end == 0.4
    assert result.duration_seconds == 1.0
    assert result.character_cost == 11
    assert result.request_id == "cart-1"
    assert result.alignment_quality["valid"] is True

    get_settings.cache_clear()


def test_gemini_tts_even_spread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    from app.config import get_settings

    get_settings.cache_clear()

    pcm = b"\x00\x00" * 24000

    class _Inline:
        data = pcm
        mime_type = "audio/L16;codec=pcm;rate=24000"

    class _Part:
        inline_data = _Inline()

    class _Content:
        parts = [_Part()]

    class _Candidate:
        content = _Content()

    class _Response:
        candidates = [_Candidate()]

    class _FakeModels:
        def generate_content(self, **kwargs: Any) -> _Response:
            assert kwargs["model"] == "gemini-3.1-flash-tts-preview"
            assert kwargs["contents"] == "Hello world"
            return _Response()

    class _FakeGenai:
        models = _FakeModels()

    client = GeminiTtsClient(
        api_key="k",
        voice_id="Kore",
        model_id="gemini-3.1-flash-tts-preview",
        client=_FakeGenai(),
    )
    result = client.synthesize_with_timestamps("Hello world")

    assert result.audio.startswith(b"RIFF")
    assert [word.word for word in result.words] == ["Hello", "world"]
    assert result.words[0].start == 0.0
    assert result.words[0].end == 0.5
    assert result.words[1].end == 1.0
    assert result.duration_seconds == 1.0
    assert result.character_cost == 11
    assert result.alignment_source == "estimated"

    get_settings.cache_clear()


def test_gemini_tts_retries_invalid_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    monkeypatch.setattr("app.services.gemini_tts_client.time.sleep", lambda _: None)
    from app.config import get_settings

    get_settings.cache_clear()

    pcm = b"\x00\x00" * 24000
    calls = {"n": 0}

    class _Inline:
        data = pcm
        mime_type = "audio/L16;codec=pcm;rate=24000"

    class _Part:
        inline_data = _Inline()

    class _Content:
        parts = [_Part()]

    class _Candidate:
        content = _Content()

    class _Response:
        candidates = [_Candidate()]

    class _FakeModels:
        def generate_content(self, **kwargs: Any) -> _Response:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError(
                    "400 INVALID_ARGUMENT. {'error': {'code': 400, "
                    "'message': 'Request contains an invalid argument.', "
                    "'status': 'INVALID_ARGUMENT'}}"
                )
            return _Response()

    class _FakeGenai:
        models = _FakeModels()

    client = GeminiTtsClient(
        api_key="k",
        voice_id="Kore",
        model_id="gemini-3.1-flash-tts-preview",
        max_retries=3,
        client=_FakeGenai(),
    )
    result = client.synthesize_with_timestamps("Hello world")
    assert calls["n"] == 2
    assert result.audio.startswith(b"RIFF")

    get_settings.cache_clear()


def test_narration_override_from_rows_accepts_cartesia() -> None:
    override = narration_override_from_rows(
        [
            {
                "stage_action": "audio_narration",
                "provider": "cartesia",
                "model": "sonic-3.6",
                "voice_id": "a5136bf9-224c-4d76-b823-52bd5efcffcc",
            },
        ],
    )
    assert override is not None
    assert override.provider == "cartesia"
    assert override.voice_id == "a5136bf9-224c-4d76-b823-52bd5efcffcc"
