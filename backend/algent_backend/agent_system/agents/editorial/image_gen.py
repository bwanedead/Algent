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

# Nano Banana 2. Lite by default — half the price for work that is decorative by
# definition, so the standard model is reserved for a hero we actually care about.
MODEL = "gemini-3.1-flash-lite-image"
MODEL_STANDARD = "gemini-3.1-flash-image"
_API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

# generateContent, not the interactions endpoint the image docs describe: interactions 404s
# for the lite model ("Requested entity was not found") while both models list
# generateContent among their supportedGenerationMethods. One endpoint for both is worth
# more than following the doc page.
def endpoint(model: str) -> str:
    return f"{_API_ROOT}/{model}:generateContent"


#: Sizes each model will actually accept. Lite is 1K-only — asking for 2K returns
#: "Image size 2K is not supported for this model", which is also why the price list
#: quotes lite at 1K only.
SIZES: dict[str, tuple[str, ...]] = {
    "gemini-3.1-flash-lite-image": ("1K",),
    "gemini-3.1-flash-image": ("1K", "2K", "4K"),
}

# 16:9 because a hero is a wide banner and the same asset is what a link preview shows.
ASPECT = "16:9"
DEFAULT_SIZE = "2K"
_ENV_SIZE = "ALGENT_HERO_IMAGE_SIZE"
_ENV_MODEL = "ALGENT_HERO_IMAGE_MODEL"

# Standard tier list prices per image (batch is ~50% less). Lite is roughly half of flash.
USD_PER_IMAGE: dict[str, float] = {
    "0.5K": 0.045,
    "1K": 0.067,
    "2K": 0.101,
    "4K": 0.151,
}
USD_PER_IMAGE_LITE: dict[str, float] = {"1K": 0.0336, "2K": 0.0505}

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
    #: The caption we authorised, if any. The review gate compares the rendered words
    #: against this — a hook that came back misspelled is worse than no hook.
    hook: str = ""
    label: str = IMAGE_LABEL

    def suffix(self) -> str:
        return ".png" if self.mime_type.endswith("png") else ".jpg"


def image_size() -> str:
    size = os.environ.get(_ENV_SIZE, DEFAULT_SIZE).strip() or DEFAULT_SIZE
    return size if size in USD_PER_IMAGE else DEFAULT_SIZE


def model_id() -> str:
    return os.environ.get(_ENV_MODEL, MODEL).strip() or MODEL


def estimated_usd(size: str | None = None, *, model: str | None = None) -> float:
    """List price for one image at this size on this model."""
    table = USD_PER_IMAGE_LITE if "lite" in (model or model_id()).lower() else USD_PER_IMAGE
    chosen = size or image_size()
    return table.get(chosen) or USD_PER_IMAGE.get(chosen, USD_PER_IMAGE[DEFAULT_SIZE])


def generate_hero_image(
    subject: str,
    *,
    setting: str = "",
    hook: str = "",
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

    prompt = build_image_prompt(subject, setting=setting, hook=hook)  # raises if unsafe
    chosen = size if size in USD_PER_IMAGE else image_size()
    key = api_key or _resolve_key()
    if not key:
        raise ImageGenerationError("no Gemini API key (GEMINI_API_KEY)")

    model = model_id()
    chosen = _supported_size(model, chosen)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": ASPECT, "imageSize": chosen},
        },
    }
    own = client is None
    http = client or httpx.Client(timeout=_TIMEOUT_S)
    try:
        response = http.post(
            endpoint(model), json=payload,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        )
        if getattr(response, "status_code", 0) != 200:
            body = (getattr(response, "text", "") or "")[:200]
            raise ImageGenerationError(f"HTTP {response.status_code}: {body}")
        body = response.json()
        data, returned_mime = _decode(body)
        usd = _metered_usd(body, chosen, model)
    except ImageGenerationError:
        raise
    except Exception as exc:  # noqa: BLE001 — one vendor shape change must not crash a rail
        raise ImageGenerationError(f"{type(exc).__name__}: {str(exc)[:160]}") from exc
    finally:
        if own:
            http.close()

    return GeneratedImage(
        data=data, mime_type=returned_mime, model=model, size=chosen, aspect=ASPECT,
        prompt=prompt, estimated_usd=usd, hook=hook.strip(),
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
    """Every plausible image-bearing block, in the order we prefer them.

    Primary shape is generateContent's ``candidates[].content.parts[].inlineData``; the
    older interactions shapes are still read because this response has moved once already
    and a silent miss is indistinguishable from a refusal.
    """
    found: list[dict] = []
    for cand in payload.get("candidates") or []:
        if not isinstance(cand, dict):
            continue
        for part in ((cand.get("content") or {}).get("parts") or []):
            if isinstance(part, dict) and isinstance(part.get("inlineData"), dict):
                inline = part["inlineData"]
                found.append({"data": inline.get("data"), "mime_type": inline.get("mimeType")})
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


# Output-token price per 1M, derived from the published per-image rates (flash 2K ≈ 1,680
# tokens ≈ $0.101; lite is about half). Metering the tokens the response actually reports
# beats a size lookup — a real 2K flash image billed 1,535 against a listed 1,680 — but the
# rate has to follow the model or lite gets charged at flash prices.
_USD_PER_1M_OUTPUT = 60.0
_USD_PER_1M_OUTPUT_LITE = 30.0


def _rate_for(model: str) -> float:
    return _USD_PER_1M_OUTPUT_LITE if "lite" in model.lower() else _USD_PER_1M_OUTPUT


def _metered_usd(payload: dict, size: str, model: str | None = None) -> float:
    """Cost from the response's own usage when present, else the per-size list price.

    Prefers the IMAGE-modality token count, which is the billed quantity: a 1K image
    reports 1,120 image tokens inside a 1,511 candidate total, and charging the total
    would overstate every image by the prompt-echo tokens.
    """
    chosen = model or model_id()
    tokens = _image_tokens(payload)
    if tokens:
        return round(tokens / 1_000_000 * _rate_for(chosen), 6)
    return estimated_usd(size, model=chosen)


def _image_tokens(payload: dict) -> int:
    if not isinstance(payload, dict):
        return 0
    usage = payload.get("usageMetadata") or payload.get("usage") or {}
    for detail in usage.get("candidatesTokensDetails") or []:
        if isinstance(detail, dict) and str(detail.get("modality")).upper() == "IMAGE":
            count = detail.get("tokenCount")
            if isinstance(count, int) and count > 0:
                return count
    for key in ("candidatesTokenCount", "total_output_tokens"):
        count = usage.get(key)
        if isinstance(count, int) and count > 0:
            return count
    return 0


def _supported_size(model: str, size: str) -> str:
    """Clamp to a size this model accepts — lite rejects anything above 1K outright."""
    allowed = SIZES.get(model)
    return size if not allowed or size in allowed else allowed[-1]


def _resolve_key() -> str | None:
    try:
        from algent_backend.config import get_provider_api_key

        return get_provider_api_key("google")
    except Exception:  # noqa: BLE001
        return os.environ.get("GEMINI_API_KEY")
