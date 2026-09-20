import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from app.llm_actions import LLM_ACTION_BY_KEY, LLM_GLOBAL_DEFAULT
from app.llm_defaults import DEFAULT_OPENAI_MODEL
from app.tts_defaults import (
    CARTESIA_MAX_SEGMENT_CHARS,
    DEFAULT_NARRATION_MODEL,
    DEFAULT_NARRATION_VOICE_ID,
    GOOGLE_TTS_MAX_SEGMENT_CHARS,
    SPEECHIFY_STREAM_MAX_CHARS,
    tts_provider_for_model,
)

API_DIR = Path(__file__).resolve().parents[1]
_DOTENV_PATH = API_DIR / ".env"
_DOTENV_MTIME: float | None = None

load_dotenv(_DOTENV_PATH)


def _refresh_dotenv_if_changed() -> None:
    """Reload .env when the file changes so dev edits apply without a restart."""
    global _DOTENV_MTIME

    if not _DOTENV_PATH.exists():
        return

    mtime = _DOTENV_PATH.stat().st_mtime
    if _DOTENV_MTIME == mtime:
        return

    load_dotenv(_DOTENV_PATH, override=True)
    _DOTENV_MTIME = mtime
    _get_settings_cached.cache_clear()


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")

    return value


def get_first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)

        if value:
            return value

    formatted_names = ", ".join(names)
    raise RuntimeError(f"Missing one of required environment variables: {formatted_names}")


def parse_csv_env(name: str, default: str) -> list[str]:
    raw_value = os.getenv(name, default)
    values = [value.strip() for value in raw_value.split(",")]

    return [value for value in values if value]


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)

    if raw is None or not raw.strip():
        return default

    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_llm_action(action: str) -> "LLMActionSettings":
    _refresh_dotenv_if_changed()
    spec = LLM_ACTION_BY_KEY.get(action)
    if spec is not None:
        provider_default, model_default = spec.provider, spec.model
        model_env = spec.model_env
    else:
        provider_default, model_default = LLM_GLOBAL_DEFAULT
        model_env = f"LLM_{action.upper()}_MODEL"

    key = action.upper()
    provider = os.getenv(f"LLM_{key}_PROVIDER", provider_default).strip().lower()
    model = os.getenv(model_env, "").strip() or model_default

    return LLMActionSettings(provider=provider, model=model)


@dataclass(frozen=True)
class SupabaseSettings:
    url: str
    publishable_key: str
    service_role_key: str


@dataclass(frozen=True)
class InfrastructureSettings:
    frontend_origins: list[str]
    redis_url: str
    sources_bucket: str
    rq_queue_name: str
    production_run_job_timeout: str
    signed_url_expires_seconds: int
    max_source_upload_bytes: int
    log_level: str


@dataclass(frozen=True)
class LLMActionSettings:
    provider: str
    model: str


@dataclass(frozen=True)
class LLMSettings:
    openai_api_key: str | None
    anthropic_api_key: str | None
    google_api_key: str | None
    anthropic_max_tokens: int
    anthropic_json_prefill: str

    def resolve_action(self, action: str) -> LLMActionSettings:
        return _resolve_llm_action(action)


@dataclass(frozen=True)
class IntellexSettings:
    llama_cloud_api_key: str | None
    llamaparse_tier: str
    source_research_max_chars: int
    web_enrichment_max_searches: int
    # Shared vector space for all embedding consumers (RAG retrieval, wiki
    # authoring evidence linking). 1536 dims = text-embedding-3-small,
    # matching the pgvector columns from migration 31.
    embedding_model: str


@dataclass(frozen=True)
class WikiAuthoringSettings:
    # Manual knowledge curation (see docs/internal/plans/wiki-authoring-contract.md).
    max_notes_chars: int
    # Evidence linking: entries embed "{label} — {definition}" and match against
    # the source's ndr_segments. Stricter than the assistant's recall threshold —
    # linking is a precision problem.
    evidence_top_k: int
    evidence_threshold: float
    evidence_weak_floor: float
    # Advisory duplicate detection against existing wiki entries.
    dedup_similarity_threshold: float
    # File-ingest: note attachments transcribed before structuring.
    max_attachment_bytes: int
    max_attachments_per_batch: int
    transcription_job_timeout: str


@dataclass(frozen=True)
class AssistantSettings:
    # RAG retrieval tuning for the Reader assistant (discussions + scenarios).
    chat_model: str
    match_threshold: float
    segment_count: int
    wiki_count: int


@dataclass(frozen=True)
class NarrationSettings:
    # Synthesized narration for the Reader (generate-narration stage).
    # Provider is inferred from model_id (simba-* → Speechify, eleven* →
    # ElevenLabs, sonic* → Cartesia, gemini* → Google).
    speechify_api_key: str | None
    elevenlabs_api_key: str | None
    cartesia_api_key: str | None
    google_api_key: str | None
    model_id: str
    voice_id: str
    output_format: str
    request_timeout_seconds: int
    max_retries: int
    elevenlabs_max_segment_chars: int
    speechify_max_segment_chars: int
    cartesia_max_segment_chars: int
    google_tts_max_segment_chars: int

    @property
    def provider(self) -> str:
        return tts_provider_for_model(self.model_id)

    @property
    def api_key(self) -> str | None:
        if self.provider == "elevenlabs":
            return self.elevenlabs_api_key
        if self.provider == "cartesia":
            return self.cartesia_api_key
        if self.provider == "google":
            return self.google_api_key
        return self.speechify_api_key

    @property
    def max_segment_chars(self) -> int:
        if self.provider == "elevenlabs":
            return self.elevenlabs_max_segment_chars
        if self.provider == "cartesia":
            return self.cartesia_max_segment_chars
        if self.provider == "google":
            return self.google_tts_max_segment_chars
        return self.speechify_max_segment_chars


@dataclass(frozen=True)
class StudySheetSettings:
    max_attempts: int


@dataclass(frozen=True)
class QnGenSettings:
    concept_batch_size: int
    critique_supporting: bool
    max_repair_turns: int
    flashcards_per_chapter_min: int
    flashcards_per_chapter_max: int
    scenarios_per_chapter_min: int
    scenarios_per_chapter_max: int


@dataclass(frozen=True)
class Settings:
    supabase: SupabaseSettings
    infra: InfrastructureSettings
    llm: LLMSettings
    intellex: IntellexSettings
    wiki_authoring: WikiAuthoringSettings
    assistant: AssistantSettings
    narration: NarrationSettings
    qngen: QnGenSettings
    study_sheet: StudySheetSettings

    # Backward-compatible flat accessors for existing call sites.
    @property
    def supabase_url(self) -> str:
        return self.supabase.url

    @property
    def supabase_publishable_key(self) -> str:
        return self.supabase.publishable_key

    @property
    def supabase_service_role_key(self) -> str:
        return self.supabase.service_role_key

    @property
    def frontend_origins(self) -> list[str]:
        return self.infra.frontend_origins

    @property
    def redis_url(self) -> str:
        return self.infra.redis_url

    @property
    def sources_bucket(self) -> str:
        return self.infra.sources_bucket

    @property
    def rq_queue_name(self) -> str:
        return self.infra.rq_queue_name

    @property
    def production_run_job_timeout(self) -> str:
        return self.infra.production_run_job_timeout

    @property
    def signed_url_expires_seconds(self) -> int:
        return self.infra.signed_url_expires_seconds

    @property
    def max_source_upload_bytes(self) -> int:
        return self.infra.max_source_upload_bytes

    @property
    def qngen_concept_batch_size(self) -> int:
        return self.qngen.concept_batch_size


@lru_cache
def _get_settings_cached() -> Settings:
    return Settings(
        supabase=SupabaseSettings(
            url=get_required_env("SUPABASE_URL").rstrip("/"),
            publishable_key=get_first_env("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY"),
            service_role_key=get_required_env("SUPABASE_SERVICE_ROLE_KEY"),
        ),
        infra=InfrastructureSettings(
            frontend_origins=parse_csv_env("FRONTEND_ORIGINS", "http://localhost:5173"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            sources_bucket=os.getenv("SOURCES_BUCKET", "sources"),
            rq_queue_name=os.getenv("RQ_QUEUE_NAME", "arsenal"),
            production_run_job_timeout=os.getenv("PRODUCTION_RUN_JOB_TIMEOUT", "2h"),
            signed_url_expires_seconds=int(os.getenv("SIGNED_URL_EXPIRES_SECONDS", "3600")),
            max_source_upload_bytes=int(
                os.getenv("MAX_SOURCE_UPLOAD_BYTES", str(100 * 1024 * 1024)),
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        ),
        llm=LLMSettings(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            google_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
            anthropic_max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "16384")),
            anthropic_json_prefill=os.getenv("ANTHROPIC_JSON_PREFILL", "auto").strip().lower(),
        ),
        intellex=IntellexSettings(
            llama_cloud_api_key=os.getenv("LLAMAPARSE_API_KEY"),
            llamaparse_tier=os.getenv("LLAMAPARSE_TIER", "agentic"),
            source_research_max_chars=int(os.getenv("SOURCE_RESEARCH_MAX_CHARS", "16000")),
            web_enrichment_max_searches=int(os.getenv("WEB_ENRICHMENT_MAX_SEARCHES", "5")),
            # EXTRACT_EMBEDDING_MODEL honored as a fallback so existing .env
            # files keep working after the extraction-era rename.
            embedding_model=os.getenv(
                "EMBEDDING_MODEL",
                os.getenv("EXTRACT_EMBEDDING_MODEL", "text-embedding-3-small"),
            ),
        ),
        wiki_authoring=WikiAuthoringSettings(
            max_notes_chars=int(os.getenv("WIKI_AUTHORING_MAX_NOTES_CHARS", "24000")),
            evidence_top_k=int(os.getenv("WIKI_AUTHORING_EVIDENCE_TOP_K", "3")),
            evidence_threshold=float(os.getenv("WIKI_AUTHORING_EVIDENCE_THRESHOLD", "0.45")),
            evidence_weak_floor=float(os.getenv("WIKI_AUTHORING_EVIDENCE_WEAK_FLOOR", "0.3")),
            dedup_similarity_threshold=float(
                os.getenv("WIKI_AUTHORING_DEDUP_SIMILARITY_THRESHOLD", "0.85"),
            ),
            max_attachment_bytes=int(
                os.getenv(
                    "WIKI_AUTHORING_MAX_ATTACHMENT_BYTES",
                    str(25 * 1024 * 1024),
                ),
            ),
            max_attachments_per_batch=int(
                os.getenv("WIKI_AUTHORING_MAX_ATTACHMENTS_PER_BATCH", "20"),
            ),
            transcription_job_timeout=os.getenv(
                "WIKI_AUTHORING_TRANSCRIPTION_JOB_TIMEOUT",
                "30m",
            ),
        ),
        assistant=AssistantSettings(
            chat_model=os.getenv("ASSISTANT_CHAT_MODEL", DEFAULT_OPENAI_MODEL),
            match_threshold=float(os.getenv("ASSISTANT_MATCH_THRESHOLD", "0.3")),
            segment_count=int(os.getenv("ASSISTANT_SEGMENT_COUNT", "8")),
            wiki_count=int(os.getenv("ASSISTANT_WIKI_COUNT", "6")),
        ),
        narration=NarrationSettings(
            speechify_api_key=os.getenv("SPEECHIFY_API_KEY"),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY"),
            cartesia_api_key=os.getenv("CARTESIA_API_KEY"),
            google_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
            model_id=os.getenv("AUDIO_NARRATION_MODEL", DEFAULT_NARRATION_MODEL),
            voice_id=os.getenv("AUDIO_NARRATION_VOICE_ID", DEFAULT_NARRATION_VOICE_ID),
            output_format=os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128"),
            request_timeout_seconds=int(os.getenv("ELEVENLABS_REQUEST_TIMEOUT_SECONDS", "600")),
            max_retries=int(os.getenv("ELEVENLABS_MAX_RETRIES", "3")),
            elevenlabs_max_segment_chars=int(os.getenv("ELEVENLABS_MAX_SEGMENT_CHARS", "9500")),
            speechify_max_segment_chars=int(
                os.getenv("SPEECHIFY_MAX_SEGMENT_CHARS", str(SPEECHIFY_STREAM_MAX_CHARS)),
            ),
            cartesia_max_segment_chars=int(
                os.getenv("CARTESIA_MAX_SEGMENT_CHARS", str(CARTESIA_MAX_SEGMENT_CHARS)),
            ),
            google_tts_max_segment_chars=int(
                os.getenv("GOOGLE_TTS_MAX_SEGMENT_CHARS", str(GOOGLE_TTS_MAX_SEGMENT_CHARS)),
            ),
        ),
        qngen=QnGenSettings(
            concept_batch_size=int(os.getenv("CONCEPT_BATCH_SIZE", "8")),
            critique_supporting=_bool_env("QNGEN_CRITIQUE_SUPPORTING", False),
            max_repair_turns=int(os.getenv("QNGEN_MAX_REPAIR_TURNS", "2")),
            flashcards_per_chapter_min=int(os.getenv("QNGEN_FLASHCARDS_PER_CHAPTER_MIN", "3")),
            flashcards_per_chapter_max=int(os.getenv("QNGEN_FLASHCARDS_PER_CHAPTER_MAX", "8")),
            scenarios_per_chapter_min=int(os.getenv("QNGEN_SCENARIOS_PER_CHAPTER_MIN", "1")),
            scenarios_per_chapter_max=int(os.getenv("QNGEN_SCENARIOS_PER_CHAPTER_MAX", "3")),
        ),
        study_sheet=StudySheetSettings(
            max_attempts=int(os.getenv("STUDY_SHEET_MAX_ATTEMPTS", "3")),
        ),
    )


def get_settings() -> Settings:
    _refresh_dotenv_if_changed()
    return _get_settings_cached()


get_settings.cache_clear = _get_settings_cached.cache_clear  # type: ignore[attr-defined]
