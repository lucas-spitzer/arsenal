"""Image generation clients for Image components (OpenAI and Google)."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import Any, Protocol

from PIL import Image

from app.config import get_settings
from app.llm_defaults import (
    GEMINI_3_PRO_IMAGE_MODEL,
    GEMINI_31_FLASH_IMAGE_MODEL,
    OPENAI_IMAGE_FLARE_MODEL,
    OPENAI_IMAGE_SUNBURST_MODEL,
)
from app.mathesys.study_material.inputs import ComponentFile

IMAGE_PROVIDERS = ("openai", "google")
IMAGE_MODELS: dict[str, tuple[str, ...]] = {
    "openai": (OPENAI_IMAGE_FLARE_MODEL, OPENAI_IMAGE_SUNBURST_MODEL),
    "google": (GEMINI_31_FLASH_IMAGE_MODEL, GEMINI_3_PRO_IMAGE_MODEL),
}
ASPECT_RATIOS = ("auto", "1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16")
OPENAI_QUALITIES = ("low", "medium", "high")
GOOGLE_IMAGE_SIZES = ("1K", "2K", "4K")

# OpenAI's Image API takes pixel sizes; map every supported ratio to the nearest one.
_OPENAI_SIZES = {
    "1:1": "1024x1024",
    "3:2": "1536x1024",
    "4:3": "1536x1024",
    "16:9": "1536x1024",
    "2:3": "1024x1536",
    "3:4": "1024x1536",
    "9:16": "1024x1536",
}


class ImageGenerationError(RuntimeError):
    """The provider returned no usable image."""


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    aspect_ratio: str
    quality: str = "high"
    image_size: str = "2K"
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
        size = _OPENAI_SIZES.get(request.aspect_ratio, "1024x1024")
        quality = request.quality if request.quality in OPENAI_QUALITIES else "high"
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
            settings={"size": size, "quality": quality, "reference_count": len(references)},
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
        image_size = request.image_size if request.image_size in GOOGLE_IMAGE_SIZES else "2K"
        contents: list[Any] = [
            types.Part.from_bytes(data=item.content, mime_type=item.mime_type)
            for item in request.references
            if item.is_image
        ]
        contents.append(request.prompt)
        response = self._client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio=aspect, image_size=image_size),
            ),
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
                "reference_count": len(contents) - 1,
            },
        )


def resolve_image_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Fill in defaults and drop anything the providers do not support."""
    settings = get_settings().study_material
    raw = raw or {}
    provider = str(raw.get("provider") or settings.image_provider).lower()
    if provider not in IMAGE_PROVIDERS:
        provider = "openai"
    default_model = settings.openai_image_model if provider == "openai" else settings.google_image_model
    model = str(raw.get("model") or default_model)
    if model not in IMAGE_MODELS[provider] and model != default_model:
        model = default_model
    aspect = str(raw.get("aspect_ratio") or "auto")
    quality = str(raw.get("quality") or "high")
    image_size = str(raw.get("image_size") or "2K")
    return {
        "provider": provider,
        "model": model,
        "aspect_ratio": aspect if aspect in ASPECT_RATIOS else "auto",
        "quality": quality if quality in OPENAI_QUALITIES else "high",
        "image_size": image_size if image_size in GOOGLE_IMAGE_SIZES else "2K",
    }


def get_image_client(provider: str, model: str) -> ImageClient:
    if provider == "google":
        return GoogleImageClient(model)
    return OpenAIImageClient(model)
