"""
Hero-image generation — the Gemini call, wrapped so the safety rules cannot be bypassed.

This is deliberately thin. Everything that decides *what* gets drawn lives in
``hero_image``: the subject guards, the prohibition block, the honesty label. This module
only turns an approved brief into bytes, and it refuses to accept a raw prompt so there is
no path that reaches the model without those guards applied.

Cost is metered per image because a hero is a *per-article* spend sitting next to a rail
that costs $0.33–$1.19, so it is a real fraction rather than a rounding error, and the
operator asked to see whether it is economically viable at all.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

from .hero_image import IMAGE_LABEL, build_image_prompt

# Nano Banana 2.
MODEL = "gemini-3.1-flash-image"
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"

# 16:9 because a hero is a wide banner and the same asset is what a link preview shows.
ASPECT = "16:9"
DEFAULT_SIZE = "2K"
_ENV_SIZE = "ALGENT_HERO_IMAGE_SIZE"
_ENV_MODEL = "ALGENT_HERO_IMAGE_MODEL"

# Published output-token prices, per image, standard tier (batch is ~50% less).
USD_PER_IMAGE: dict[str, float] = {
    "0.5K": 0.045,
    "1K": 0.067,
    "2K": 0.101,
    "4K": 0.151,
}

_TIMEOUT_S = 120.0


class ImageGenerationError(RuntimeError):
    """The image could not be generated. Callers ship the article without a hero."""


@dataclass(frozen=True)
class GeneratedImage:
    """Bytes plus everything the ledger needs to account for them."""

    data: bytes
    mime_type: str
    model: str
    size: str
    aspect: str
    prompt: str
    estimated_usd: float
    label: str = IMAGE_LABEL

    def suffix(self) -> str:
        return ".png" if self.mime_type.endswith("png") else ".jpg"


def image_size() -> str:
    size = os.environ.get(_ENV_SIZE, DEFAULT_SIZE).strip() or DEFAULT_SIZE
    return size if size in USD_PER_IMAGE else DEFAULT_SIZE


def model_id() -> str:
    return os.environ.get(_ENV_MODEL, MODEL).strip() or MODEL


def estimated_usd(size: str | None = None) -> float:
    return USD_PER_IMAGE.get(size or image_size(), USD_PER_IMAGE[DEFAULT_SIZE])


def generate_hero_image(
    subject: str,
    *,
    setting: str = "",
    size: str | None = None,
    mime_type: str = "image/jpeg",
    api_key: str | None = None,
    client: Any | None = None,
) -> GeneratedImage:
    """Draw a hero image for ``subject``. Raises :class:`ImageGenerationError` on failure.

    Takes a *subject*, never a prompt: the prohibitions and the subject guards are applied
    here by construction, so there is no call path that skips them. A subject the guards
    reject raises ``UnsafeImageSubject`` before any spend.
    """
    import httpx

    prompt = build_image_prompt(subject, setting=setting)   # raises on an unsafe subject
    chosen = size if size in USD_PER_IMAGE else image_size()
    key = api_key or _resolve_key()
    if not key:
        raise ImageGenerationError("no Gemini API key (GEMINI_API_KEY)")

    payload = {
        "model": model_id(),
        "input": [{"type": "text", "text": prompt}],
        "response_format": {
            "type": "image",
            "mime_type": mime_type,
            "aspect_ratio": ASPECT,
            "image_size": chosen,
        },
    }
    own = client is None
    http = client or httpx.Client(timeout=_TIMEOUT_S)
    try:
        response = http.post(
            ENDPOINT, json=payload,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        )
        if getattr(response, "status_code", 0) != 200:
            body = (getattr(response, "text", "") or "")[:200]
            raise ImageGenerationError(f"HTTP {response.status_code}: {body}")
        payload = response.json()
        data, returned_mime = _decode(payload)
        usd = _metered_usd(payload, chosen)
    except ImageGenerationError:
        raise
    except Exception as exc:  # noqa: BLE001 — one vendor shape change must not crash a rail
        raise ImageGenerationError(f"{type(exc).__name__}: {str(exc)[:160]}") from exc
    finally:
        if own:
            http.close()

    return GeneratedImage(
        data=data, mime_type=returned_mime, model=model_id(), size=chosen, aspect=ASPECT,
        prompt=prompt, estimated_usd=usd,
    )


def _decode(payload: dict) -> tuple[bytes, str]:
    """Pull ``(bytes, mime_type)`` out of an interactions response.

    The live shape is ``steps[] -> {type: model_output} -> content[] -> {type: image, data}``,
    which is **not** the ``output_image.data`` accessor the docs describe — verified against a
    real 200. Both are tried, plus the flat ``output`` list, because this response shape has
    already moved once and a silent miss looks identical to a refusal. An empty result raises
    rather than writing a zero-byte file onto the site.
    """
    if not isinstance(payload, dict):
        raise ImageGenerationError("response was not an object")

    for block in _image_blocks(payload):
        encoded = block.get("data") or (block.get("inline_data") or {}).get("data")
        if encoded:
            mime = str(block.get("mime_type") or "image/jpeg")
            try:
                return base64.b64decode(encoded), mime
            except Exception as exc:  # noqa: BLE001
                raise ImageGenerationError(f"undecodable image: {str(exc)[:80]}") from exc
    raise ImageGenerationError("response carried no image data")


def _image_blocks(payload: dict) -> list[dict]:
    """Every plausible image-bearing block, in the order we prefer them."""
    found: list[dict] = []
    convenience = payload.get("output_image")
    if isinstance(convenience, dict):
        found.append(convenience)
    for step in payload.get("steps") or []:
        if isinstance(step, dict) and step.get("type") == "model_output":
            found += [
                c for c in (step.get("content") or [])
                if isinstance(c, dict) and c.get("type") in ("image", "output_image")
            ]
    found += [
        c for c in (payload.get("output") or [])
        if isinstance(c, dict) and c.get("type") in ("image", "output_image")
    ]
    return found


# Output-token price for the image model, USD per 1M tokens, derived from the published
# per-image rates (2K ≈ 1,680 output tokens ≈ $0.101). Metering the tokens the response
# actually reports beats a size lookup: a real 2K generation came back at 1,535.
_USD_PER_1M_OUTPUT = 60.0


def _metered_usd(payload: dict, size: str) -> float:
    """Cost from the response's own usage when present, else the per-size list price."""
    usage = payload.get("usage") if isinstance(payload, dict) else None
    tokens = (usage or {}).get("total_output_tokens") if isinstance(usage, dict) else None
    if isinstance(tokens, int) and tokens > 0:
        return round(tokens / 1_000_000 * _USD_PER_1M_OUTPUT, 6)
    return estimated_usd(size)


def _resolve_key() -> str | None:
    try:
        from algent_backend.config import get_provider_api_key

        return get_provider_api_key("google")
    except Exception:  # noqa: BLE001
        return os.environ.get("GEMINI_API_KEY")
