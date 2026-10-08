# Shared LLM defaults — kept outside app.services.llm to avoid import cycles with config.
HAIKU_55_MODEL = "claude-haiku-5-5"
SONNET_55_MODEL = "claude-sonnet-5-5"
OPUS_55_MODEL = "claude-opus-5-5"
GPT_6_ASTRA_MODEL = "gpt-6-astra"
GPT_6_SOL_MODEL = "gpt-6.1-sol"
GPT_6_LUNA_MODEL = "gpt-6-luna"
GEMINI_38_FLASH_MODEL = "gemini-3.8-flash"
GEMINI_31_PRO_MODEL = "gemini-3.1-pro-preview"
# Image generation (Study Material image components).
OPENAI_IMAGE_FLARE_MODEL = "gpt-image-2.5-flare"
OPENAI_IMAGE_SUNBURST_MODEL = "gpt-image-2.5-sunburst"
GEMINI_31_FLASH_IMAGE_MODEL = "gemini-3.1-flash-image"
GEMINI_3_PRO_IMAGE_MODEL = "gemini-3-pro-image"
# Constructor fallback when an OpenAI client is built without a model.
# Per-action defaults live in env vars (SOURCE_RESEARCH_MODEL, etc.).
DEFAULT_OPENAI_MODEL = GPT_6_LUNA_MODEL

# Stable names for local .env. A version bump changes the id on the right.
# The name on the left stays, so that file does not need a matching edit.
MODEL_FAMILIES: dict[str, str] = {
    "astra": GPT_6_ASTRA_MODEL,
    "luna": GPT_6_LUNA_MODEL,
    "sol": GPT_6_SOL_MODEL,
    "haiku": HAIKU_55_MODEL,
    "opus": OPUS_55_MODEL,
    "sonnet": SONNET_55_MODEL,
    "gemini-flash": GEMINI_38_FLASH_MODEL,
    "gemini-pro": GEMINI_31_PRO_MODEL,
}
