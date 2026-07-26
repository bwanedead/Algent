"""Offline tests for hero-image generation — no network, real response shapes."""

from __future__ import annotations

import base64

import pytest

from algent_backend.agent_system.agents.editorial.hero_image import UnsafeImageSubject
from algent_backend.agent_system.agents.editorial.image_gen import (
    ImageGenerationError,
    _decode,
    _metered_usd,
    generate_hero_image,
)

_PIXEL = base64.b64encode(b"\xff\xd8\xff\xe0jpegbytes").decode()


def _live_shape(mime: str = "image/jpeg", image_tokens: int = 1120) -> dict:
    """What generateContent actually returns for an image."""
    return {
        "candidates": [{"content": {"parts": [{"inlineData": {"mimeType": mime, "data": _PIXEL}}]}}],
        "usageMetadata": {
            "promptTokenCount": 12,
            "candidatesTokenCount": image_tokens + 391,   # image tokens + prompt echo
            "candidatesTokensDetails": [{"modality": "IMAGE", "tokenCount": image_tokens}],
        },
    }


def _interactions_shape(mime: str = "image/jpeg") -> dict:
    """The older interactions shape, still read so a rollback doesn't silently break."""
    return {
        "usage": {"total_output_tokens": 1535},
        "steps": [{"type": "model_output",
                   "content": [{"type": "image", "mime_type": mime, "data": _PIXEL}]}],
    }


class _Resp:
    def __init__(self, payload, status=200, text=""):
        self._p, self.status_code, self.text = payload, status, text

    def json(self):
        return self._p


class _Client:
    def __init__(self, resp):
        self._r, self.calls = resp, []

    def post(self, url, json=None, headers=None):
        self.calls.append(json)
        return self._r

    def close(self):
        pass


def test_decodes_the_shape_the_api_actually_returns() -> None:
    """The docs describe output_image.data; a real 200 nests it under steps[]. Both work."""
    data, mime = _decode(_live_shape())
    assert data.startswith(b"\xff\xd8\xff") and mime == "image/jpeg"

    documented = {"output_image": {"data": _PIXEL, "mime_type": "image/png"}}
    data, mime = _decode(documented)
    assert data.startswith(b"\xff\xd8\xff") and mime == "image/png"


def test_a_response_with_no_image_raises_rather_than_writing_an_empty_file() -> None:
    with pytest.raises(ImageGenerationError, match="no image data"):
        _decode({"status": "completed", "steps": [{"type": "thought"}]})


def test_cost_uses_the_image_tokens_not_the_candidate_total() -> None:
    """A 1K image reports 1,120 IMAGE tokens inside a larger candidate total; billing the
    total would overstate every image by the prompt-echo tokens."""
    flash = "gemini-3.1-flash-image"
    assert _metered_usd(_live_shape(image_tokens=1120), "1K", flash) == pytest.approx(0.0672, abs=0.001)
    # Falls back to the list price when the vendor omits usage.
    assert _metered_usd({}, "2K", flash) == pytest.approx(0.101)


def test_lite_is_billed_at_the_lite_rate_not_the_flash_rate() -> None:
    """Same tokens, half the price — metering has to follow the model or lite costs 2x."""
    lite = "gemini-3.1-flash-lite-image"
    flash = "gemini-3.1-flash-image"
    assert _metered_usd(_live_shape(), "1K", lite) == pytest.approx(
        _metered_usd(_live_shape(), "1K", flash) / 2, rel=0.01
    )
    assert _metered_usd({}, "1K", lite) == pytest.approx(0.0336)


def test_lite_is_clamped_to_1k_because_it_rejects_anything_larger() -> None:
    """Asking lite for 2K returns 'Image size 2K is not supported for this model'."""
    from algent_backend.agent_system.agents.editorial.image_gen import _supported_size

    assert _supported_size("gemini-3.1-flash-lite-image", "2K") == "1K"
    assert _supported_size("gemini-3.1-flash-image", "2K") == "2K"


def test_generation_sends_the_guarded_prompt_and_never_the_raw_subject_alone() -> None:
    client = _Client(_Resp(_live_shape()))
    img = generate_hero_image("an orca surfacing in coastal water", client=client)

    sent = client.calls[0]["contents"][0]["parts"][0]["text"]
    assert sent.startswith("an orca surfacing in coastal water.")
    # The prohibitions are attached by the builder, not by the caller.
    assert "Do not render any text" in sent and "Do not render charts" in sent
    assert client.calls[0]["generationConfig"]["imageConfig"]["aspectRatio"] == "16:9"
    assert img.estimated_usd > 0 and img.label.startswith("AI-generated")


def test_an_unsafe_subject_is_refused_before_any_spend() -> None:
    """The guards sit in front of the network call, so a bad subject costs nothing."""
    client = _Client(_Resp(_live_shape()))
    with pytest.raises(UnsafeImageSubject):
        generate_hero_image("Florida's $1.8 trillion economy claim", client=client)
    assert client.calls == []   # never reached the API


def test_a_non_200_is_a_clean_error() -> None:
    client = _Client(_Resp({}, status=429, text="quota exceeded"))
    with pytest.raises(ImageGenerationError, match="429"):
        generate_hero_image("an orca surfacing in coastal water", client=client)
