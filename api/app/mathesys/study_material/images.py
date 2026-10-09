"""Image generation clients for Image components (OpenAI and Google)."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from PIL import Image

from app.config import get_settings
from app.llm_defaults import (
    GEMINI_3_PRO_IMAGE_MODEL,
    GEMINI_NANO_BANANA_21_MODEL,
    GROK_IMAGINE_IMAGE_2_MODEL,
    OPENAI_IMAGE_FLARE_MODEL,
    OPENAI_IMAGE_SUNBURST_MODEL,
)
from app.mathesys.study_material.inputs import ComponentFile

IMAGE_PROVIDERS = ("openai", "google", "xai")
IMAGE_MODELS: dict[str, tuple[str, ...]] = {
    "openai": (OPENAI_IMAGE_FLARE_MODEL, OPENAI_IMAGE_SUNBURST_MODEL),
    "google": (GEMINI_NANO_BANANA_21_MODEL, GEMINI_3_PRO_IMAGE_MODEL),
    "xai": (GROK_IMAGINE_IMAGE_2_MODEL,),
}
ASPECT_RATIOS = ("auto", "1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16")
OPENAI_QUALITIES = ("low", "medium", "high", "xhigh", "max")
OPENAI_RESOLUTIONS = ("1K", "2K", "4K")
GOOGLE_FLASH_SIZES = ("0.5K", "1K", "2K", "4K")
GOOGLE_PRO_SIZES = ("1K", "2K", "4K")
GOOGLE_IMAGE_SIZES = GOOGLE_FLASH_SIZES
GOOGLE_THINKING_LEVELS = ("minimal", "medium", "high")
XAI_QUALITIES = ("low", "medium")
XAI_RESOLUTIONS = ("1K", "1.5K", "2K")
DEFAULT_OPENAI_QUALITY = "high"
DEFAULT_OPENAI_RESOLUTION = "1K"
DEFAULT_GOOGLE_IMAGE_SIZE = "2K"
DEFAULT_GOOGLE_THINKING = "medium"
DEFAULT_XAI_QUALITY = "medium"
DEFAULT_XAI_RESOLUTION = "1K"
XAI_IMAGE_GENERATIONS_URL = "https://api.x.ai/v1/images/generations"
XAI_IMAGE_EDITS_URL = "https://api.x.ai/v1/images/edits"
XAI_MAX_REFERENCE_IMAGES = 5

# OpenAI takes pixel sizes. 1K keeps the sizes already used for these ratios.
# 2K and 4K stay inside the Image API limits: edges are multiples of 16, no
# edge exceeds 3840, and the pixel count stays between 655,360 and 8,294,400.
# Square 4K stops at 2880x2880, the largest legal square.
_OPENAI_PIXEL_SIZES: dict[str, dict[str, str]] = {
    "1K": {
        "1:1": "1024x1024",
        "3:2": "1536x1024",
        "4:3": "1536x1024",
        "16:9": "1536x1024",
        "2:3": "1024x1536",
        "3:4": "1024x1536",
        "9:16": "1024x1536",
    },
    "2K": {
        "1:1": "2048x2048",
        "3:2": "2016x1344",
        "4:3": "2048x1536",
        "16:9": "2048x1152",
        "2:3": "1344x2016",
        "3:4": "1536x2048",
        "9:16": "1152x2048",
    },
    "4K": {
        "1:1": "2880x2880",
        "3:2": "2880x1920",
        "4:3": "2880x2160",
        "16:9": "3840x2160",
        "2:3": "1920x2880",
        "3:4": "2160x2880",
        "9:16": "2160x3840",
    },
}


def openai_pixel_size(aspect_ratio: str, resolution: str) -> str:
    """Pixel size for an OpenAI image at the given aspect and resolution tier."""
    tier = resolution if resolution in _OPENAI_PIXEL_SIZES else DEFAULT_OPENAI_RESOLUTION
    sizes = _OPENAI_PIXEL_SIZES[tier]
    return sizes.get(aspect_ratio, sizes["1:1"])


def google_sizes_for_model(model: str) -> tuple[str, ...]:
    """Resolutions this Google image model accepts. Neither current model offers 0.5K."""
    sizes = {
        GEMINI_NANO_BANANA_21_MODEL: GOOGLE_PRO_SIZES,
        GEMINI_3_PRO_IMAGE_MODEL: GOOGLE_PRO_SIZES,
    }
    return sizes.get(model, GOOGLE_PRO_SIZES)


def google_api_image_size(image_size: str) -> str:
    """Gemini's image_size value. 0.5K is sent as 512."""
    if image_size == "0.5K":
        return "512"
    return image_size


def image_control_catalog() -> dict[str, Any]:
    """Quality and resolution options for the design-tab image controls."""
    openai = {
        "qualities": list(OPENAI_QUALITIES),
        "resolutions": list(OPENAI_RESOLUTIONS),
    }
    return {
        "openai": openai,
        "google": {
            GEMINI_NANO_BANANA_21_MODEL: {
                "qualities": list(GOOGLE_THINKING_LEVELS),
                "resolutions": list(GOOGLE_PRO_SIZES),
            },
            GEMINI_3_PRO_IMAGE_MODEL: {
                "qualities": [],
                "resolutions": list(GOOGLE_PRO_SIZES),
            },
        },
        "xai": {
            "qualities": list(XAI_QUALITIES),
            "resolutions": list(XAI_RESOLUTIONS),
        },
    }


def stage_image_options(provider: str, model: str) -> tuple[tuple[str, ...], str]:
    """Quality choices and the default for a stage image model.

    Quality is OpenAI's quality scale, Nano Banana thinking (minimal, medium, or high),
    or Grok Imagine's low and medium.
    """
    normalized = (provider or "").strip().lower()
    if normalized == "google":
        if model == GEMINI_NANO_BANANA_21_MODEL:
            return GOOGLE_THINKING_LEVELS, DEFAULT_GOOGLE_THINKING
        return (), ""
    if normalized == "xai":
        return XAI_QUALITIES, DEFAULT_XAI_QUALITY
    return OPENAI_QUALITIES, DEFAULT_OPENAI_QUALITY


def effective_stage_image_quality(provider: str, model: str, quality: str | None) -> str:
    """Quality for a stage row. Blank or illegal values use the model default."""
    qualities, default_quality = stage_image_options(provider, model)
    chosen_quality = (quality or "").strip().lower()
    if chosen_quality not in qualities:
        return default_quality
    return chosen_quality


def normalize_stage_image_quality(provider: str, model: str, quality: str | None) -> str | None:
    """Quality to store. None when the choice is not offered for the model."""
    qualities, default_quality = stage_image_options(provider, model)
    chosen_quality = (quality or "").strip().lower() or default_quality
    if chosen_quality not in qualities:
        return None
    return chosen_quality


class ImageGenerationError(RuntimeError):
    """The provider returned no usable image."""


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    aspect_ratio: str
    quality: str = DEFAULT_OPENAI_QUALITY
    resolution: str = DEFAULT_OPENAI_RESOLUTION
    image_size: str = DEFAULT_GOOGLE_IMAGE_SIZE
    thinking_level: str | None = None
    references: list[ComponentFile] = field(default_factory=list)


@dataclass(frozen=True)
class ImageResult:
    data: bytes
    mime_type: str
    width: int
    height: int
    model: str
    provider: str
    token_usage: dict[str, int]
    settings: dict[str, Any]


class ImageClient(Protocol):
    provider: str
    model: str

    def generate(self, request: ImageRequest) -> ImageResult: ...


def _dimensions(data: bytes) -> tuple[int, int, str]:
    with Image.open(io.BytesIO(data)) as image:
        fmt = (image.format or "PNG").lower()
        return image.width, image.height, "image/jpeg" if fmt in {"jpeg", "jpg"} else f"image/{fmt}"


class OpenAIImageClient:
    provider = "openai"

    def __init__(self, model: str) -> None:
        from openai import OpenAI

        api_key = get_settings().llm.openai_api_key
        if not api_key:
            raise RuntimeError("Missing required environment variable: OPENAI_API_KEY")
        self.model = model
        self._client = OpenAI(api_key=api_key)

    def generate(self, request: ImageRequest) -> ImageResult:
        resolution = (
            request.resolution
            if request.resolution in OPENAI_RESOLUTIONS
            else DEFAULT_OPENAI_RESOLUTION
        )
        size = openai_pixel_size(request.aspect_ratio, resolution)
        quality = request.quality if request.quality in OPENAI_QUALITIES else DEFAULT_OPENAI_QUALITY
        common: dict[str, Any] = {
            "model": self.model,
            "prompt": request.prompt,
            "size": size,
            "quality": quality,
            "output_format": "png",
            "background": "opaque",
        }
        references = [item for item in request.references if item.is_image]
        if references:
            response = self._client.images.edit(
                image=[(item.filename, item.content, item.mime_type) for item in references],
                **common,
            )
        else:
            response = self._client.images.generate(**common)

        if not response.data or not response.data[0].b64_json:
            raise ImageGenerationError("OpenAI returned no image data.")
        data = base64.b64decode(response.data[0].b64_json)
        width, height, mime = _dimensions(data)
        usage = response.usage
        token_usage = {
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        }
        token_usage["total_tokens"] = token_usage["input_tokens"] + token_usage["output_tokens"]
        return ImageResult(
            data=data,
            mime_type=mime,
            width=width,
            height=height,
            model=self.model,
            provider=self.provider,
            token_usage=token_usage,
            settings={
                "size": size,
                "quality": quality,
                "resolution": resolution,
                "reference_count": len(references),
            },
        )


class GoogleImageClient:
    provider = "google"

    def __init__(self, model: str) -> None:
        from google import genai

        api_key = get_settings().llm.google_api_key
        if not api_key:
            raise RuntimeError("Missing required environment variable: GEMINI_API_KEY")
        self.model = model
        self._client = genai.Client(api_key=api_key)

    def generate(self, request: ImageRequest) -> ImageResult:
        from google.genai import types

        aspect = request.aspect_ratio if request.aspect_ratio in ASPECT_RATIOS[1:] else "1:1"
        allowed_sizes = google_sizes_for_model(self.model)
        image_size = request.image_size if request.image_size in allowed_sizes else DEFAULT_GOOGLE_IMAGE_SIZE
        if image_size not in allowed_sizes:
            image_size = DEFAULT_GOOGLE_IMAGE_SIZE
        thinking_level = request.thinking_level if request.thinking_level in GOOGLE_THINKING_LEVELS else None
        send_thinking = self.model == GEMINI_NANO_BANANA_21_MODEL and thinking_level in GOOGLE_THINKING_LEVELS
        contents: list[Any] = [
            types.Part.from_bytes(data=item.content, mime_type=item.mime_type)
            for item in request.references
            if item.is_image
        ]
        contents.append(request.prompt)
        config_kwargs: dict[str, Any] = {
            "response_modalities": ["IMAGE"],
            "image_config": types.ImageConfig(
                aspect_ratio=aspect,
                image_size=google_api_image_size(image_size),
            ),
        }
        if send_thinking:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)
        response = self._client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        data: bytes | None = None
        for candidate in response.candidates or []:
            for part in getattr(candidate.content, "parts", None) or []:
                inline = getattr(part, "inline_data", None)
                if inline is not None and inline.data:
                    data = inline.data if isinstance(inline.data, bytes) else base64.b64decode(inline.data)
                    break
            if data:
                break
        if not data:
            raise ImageGenerationError("Gemini returned no image data.")

        width, height, mime = _dimensions(data)
        usage = getattr(response, "usage_metadata", None)
        input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
        return ImageResult(
            data=data,
            mime_type=mime,
            width=width,
            height=height,
            model=self.model,
            provider=self.provider,
            token_usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            settings={
                "aspect_ratio": aspect,
                "image_size": image_size,
                "thinking_level": thinking_level if send_thinking else None,
                "reference_count": len(contents) - 1,
            },
        )


def xai_image_call(model: str, request: ImageRequest) -> tuple[str, dict[str, Any]]:
    """URL and JSON body for one Grok Imagine generation or edit.

    The OpenAI SDK's multipart ``images.edit`` is not accepted by xAI.
    Reference images go in the JSON body as data URIs.
    """
    quality = request.quality if request.quality in XAI_QUALITIES else DEFAULT_XAI_QUALITY
    resolution = request.resolution if request.resolution in XAI_RESOLUTIONS else DEFAULT_XAI_RESOLUTION
    aspect = request.aspect_ratio if request.aspect_ratio in ASPECT_RATIOS else "1:1"
    references = [item for item in request.references if item.is_image]
    if len(references) > XAI_MAX_REFERENCE_IMAGES:
        raise ImageGenerationError(
            f"Grok Imagine accepts at most {XAI_MAX_REFERENCE_IMAGES} reference images.",
        )
    body: dict[str, Any] = {
        "model": model,
        "prompt": request.prompt,
        "aspect_ratio": aspect,
        "resolution": resolution.lower(),
        "quality": quality,
        "response_format": "b64_json",
    }
    if not references:
        body["n"] = 1
        return XAI_IMAGE_GENERATIONS_URL, body
    encoded = [
        {
            "type": "image_url",
            "url": f"data:{item.mime_type};base64,{base64.b64encode(item.content).decode('ascii')}",
        }
        for item in references
    ]
    if len(encoded) == 1:
        body["image"] = encoded[0]
    else:
        body["images"] = encoded
    return XAI_IMAGE_EDITS_URL, body


def _xai_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str) and error:
            return error
    text = response.text.strip()
    return text[:300] or f"HTTP {response.status_code}"


def _xai_image_bytes(payload: dict[str, Any]) -> bytes:
    if payload.get("respect_moderation") is False:
        raise ImageGenerationError("xAI filtered the generated image.")
    items = payload.get("data")
    item = items[0] if isinstance(items, list) and items else None
    if not isinstance(item, dict):
        raise ImageGenerationError("xAI returned no image data.")
    if item.get("respect_moderation") is False:
        raise ImageGenerationError("xAI filtered the generated image.")
    encoded = item.get("b64_json")
    if isinstance(encoded, str) and encoded:
        return base64.b64decode(encoded)
    url = item.get("url")
    if isinstance(url, str) and url.startswith("https://"):
        downloaded = httpx.get(url, timeout=60, follow_redirects=True)
        downloaded.raise_for_status()
        return downloaded.content
    raise ImageGenerationError("xAI returned no image data.")


class XAIImageClient:
    provider = "xai"

    def __init__(self, model: str) -> None:
        api_key = get_settings().llm.xai_api_key
        if not api_key:
            raise RuntimeError("Missing required environment variable: XAI_API_KEY")
        self.model = model
        self._api_key = api_key

    def generate(self, request: ImageRequest) -> ImageResult:
        url, body = xai_image_call(self.model, request)
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=body,
            timeout=180,
        )
        if response.status_code >= 400:
            raise ImageGenerationError(f"xAI image request failed: {_xai_error_message(response)}")
        data = _xai_image_bytes(response.json())
        width, height, mime = _dimensions(data)
        quality = str(body["quality"])
        resolution = request.resolution if request.resolution in XAI_RESOLUTIONS else DEFAULT_XAI_RESOLUTION
        reference_count = len([item for item in request.references if item.is_image])
        return ImageResult(
            data=data,
            mime_type=mime,
            width=width,
            height=height,
            model=self.model,
            provider=self.provider,
            token_usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            settings={
                "aspect_ratio": body["aspect_ratio"],
                "quality": quality,
                "resolution": resolution,
                "reference_count": reference_count,
            },
        )


def _env_image_model(provider: str) -> str:
    settings = get_settings().study_material
    if provider == "openai":
        return settings.openai_image_model
    if provider == "xai":
        return settings.xai_image_model
    return settings.google_image_model


def _chosen(
    raw: dict[str, Any],
    key: str,
    fallback: str | None,
    allowed: tuple[str, ...],
    default: str,
) -> str:
    explicit = str(raw.get(key) or "").strip()
    if explicit:
        return explicit if explicit in allowed else default
    if fallback and fallback in allowed:
        return fallback
    return default


def resolve_image_settings(
    raw: dict[str, Any] | None,
    *,
    default_provider: str | None = None,
    default_model: str | None = None,
    default_quality: str | None = None,
) -> dict[str, Any]:
    """Fill in defaults and drop anything the providers do not support.

    The workspace Design Image choice applies when the component omits that
    field. Env settings fill anything still missing. An explicit component
    value is kept.
    """
    settings = get_settings().study_material
    raw = raw or {}
    env_provider = settings.image_provider if settings.image_provider in IMAGE_PROVIDERS else "openai"
    workspace_provider = (default_provider or "").strip().lower()
    workspace_model = (default_model or "").strip()
    workspace = (
        (workspace_provider, workspace_model)
        if workspace_provider in IMAGE_PROVIDERS and workspace_model
        else None
    )
    explicit_provider = str(raw.get("provider") or "").strip().lower()
    explicit_model = str(raw.get("model") or "").strip()

    if explicit_model:
        provider = explicit_provider if explicit_provider in IMAGE_PROVIDERS else env_provider
        model = explicit_model
    elif explicit_provider in IMAGE_PROVIDERS:
        provider = explicit_provider
        if workspace is not None and workspace[0] == provider:
            model = workspace[1]
        else:
            model = _env_image_model(provider)
    elif workspace is not None:
        provider, model = workspace
    else:
        provider = env_provider
        model = _env_image_model(provider)

    if model == "gemini-3.1-flash-image":
        model = GEMINI_NANO_BANANA_21_MODEL
    env_model = _env_image_model(provider)
    if model not in IMAGE_MODELS[provider] and model != env_model:
        model = env_model
    aspect = str(raw.get("aspect_ratio") or "auto")
    if provider == "xai":
        quality = _chosen(raw, "quality", default_quality, XAI_QUALITIES, DEFAULT_XAI_QUALITY)
        resolution = _chosen(raw, "resolution", None, XAI_RESOLUTIONS, DEFAULT_XAI_RESOLUTION)
    else:
        quality = _chosen(raw, "quality", default_quality, OPENAI_QUALITIES, DEFAULT_OPENAI_QUALITY)
        resolution = _chosen(raw, "resolution", None, OPENAI_RESOLUTIONS, DEFAULT_OPENAI_RESOLUTION)
    image_size = _chosen(raw, "image_size", None, GOOGLE_FLASH_SIZES, DEFAULT_GOOGLE_IMAGE_SIZE)
    if provider == "google" and image_size == "0.5K":
        image_size = "1K"
    elif image_size not in GOOGLE_FLASH_SIZES:
        image_size = DEFAULT_GOOGLE_IMAGE_SIZE
    explicit_thinking = str(raw.get("thinking_level") or "").strip().lower()
    if provider == "google" and model == GEMINI_NANO_BANANA_21_MODEL:
        if explicit_thinking:
            thinking_level = (
                explicit_thinking
                if explicit_thinking in GOOGLE_THINKING_LEVELS
                else DEFAULT_GOOGLE_THINKING
            )
        elif default_quality and default_quality in GOOGLE_THINKING_LEVELS:
            thinking_level = default_quality
        else:
            thinking_level = DEFAULT_GOOGLE_THINKING
    else:
        thinking_level = ""
    return {
        "provider": provider,
        "model": model,
        "aspect_ratio": aspect if aspect in ASPECT_RATIOS else "auto",
        "quality": quality,
        "resolution": resolution,
        "image_size": image_size,
        "thinking_level": thinking_level or None,
    }


def get_image_client(provider: str, model: str) -> ImageClient:
    if provider == "google":
        return GoogleImageClient(model)
    if provider == "xai":
        return XAIImageClient(model)
    return OpenAIImageClient(model)
