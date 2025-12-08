"""
Abstract provider definition.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ModelResponse:
    """Generic response payload."""

    text: str
    raw: Any | None = None


class BaseModelProvider:
    """Base synchronous interface."""

    name = "base"

    def __init__(self, **_: object) -> None:
        """Accept provider-specific kwargs without enforcing structure here."""

    def generate(self, prompt: str, **kwargs) -> ModelResponse:  # pragma: no cover - interface
        raise NotImplementedError

    async def agenerate(self, prompt: str, **kwargs) -> ModelResponse:  # pragma: no cover - interface
        raise NotImplementedError
