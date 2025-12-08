"""
Abstract provider definition.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List


@dataclass
class ModelResponse:
    """Generic response payload."""

    text: str
    raw: Any | None = None


class BaseModelProvider:
    """Base synchronous interface."""

    name = "base"

    def generate(self, prompt: str, **kwargs) -> ModelResponse:
        raise NotImplementedError

    async def agenerate(self, prompt: str, **kwargs) -> ModelResponse:
        raise NotImplementedError
