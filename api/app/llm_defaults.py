# Shared LLM defaults — kept outside app.services.llm to avoid import cycles with config.
HAIKU_45_MODEL = "claude-haiku-4-5-20251001"
SONNET_5_MODEL = "claude-sonnet-5"
OPUS_55_MODEL = "claude-opus-5-5"
GPT_6_ASTRA_MODEL = "gpt-6-astra"
GPT_6_SOL_MODEL = "gpt-6-sol"
GPT_6_LUNA_MODEL = "gpt-6-luna"
GEMINI_37_FLASH_MODEL = "gemini-3.7-flash"
# Image generation (Study Material image components).
OPENAI_IMAGE_FLARE_MODEL = "gpt-image-2.5-flare"
OPENAI_IMAGE_SUNBURST_MODEL = "gpt-image-2.5-sunburst"
GEMINI_31_FLASH_IMAGE_MODEL = "gemini-3.1-flash-image"
GEMINI_3_PRO_IMAGE_MODEL = "gemini-3-pro-image"
# Constructor fallback when an OpenAI client is built without a model.
# Per-action defaults live in env vars (SOURCE_RESEARCH_MODEL, etc.).
DEFAULT_OPENAI_MODEL = GPT_6_LUNA_MODEL
