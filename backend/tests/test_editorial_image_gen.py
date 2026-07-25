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


def _live_shape(mime: str = "image/jpeg") -> dict:
    """The shape a real 200 actually returns — steps[] -> model_output -> content[]."""
    return {
        "status": "completed",
        "usage": {"total_output_tokens": 1535},
        "steps": [
            {"type": "thought", "signature": "..."},
            {"type": "model_output",
             "content": [{"type": "image", "mime_type": mime, "data": _PIXEL}]},
        ],
        "model": "gemini-3.1-flash-image",
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


def test_cost_is_metered_from_reported_tokens_not_a_size_table() -> None:
    # A real 2K generation reported 1,535 output tokens, not the listed 1,680.
    assert _metered_usd(_live_shape(), "2K") == pytest.approx(0.0921, abs=0.002)
    # Falls back to the list price when the vendor omits usage.
    assert _metered_usd({}, "2K") == pytest.approx(0.101)


def test_generation_sends_the_guarded_prompt_and_never_the_raw_subject_alone() -> None:
    client = _Client(_Resp(_live_shape()))
    img = generate_hero_image("an orca surfacing in coastal water", client=client)

    sent = client.calls[0]["input"][0]["text"]
    assert sent.startswith("an orca surfacing in coastal water.")
    # The prohibitions are attached by the builder, not by the caller.
    assert "Do not render any text" in sent and "Do not render charts" in sent
    assert client.calls[0]["response_format"]["aspect_ratio"] == "16:9"
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
