"""
OpenAI provider stub.

This module intentionally avoids importing the SDK to keep dependencies optional.
"""
from dataclasses import dataclass, field
import os

from .base_provider import BaseModelProvider, ModelResponse
from algent_backend.config import get_provider_api_key


@dataclass
class OpenAIConfig:
    """Configuration for OpenAI models."""

    api_key: str | None = field(default_factory=lambda: get_provider_api_key("openai"))
    base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))


class OpenAIProvider(BaseModelProvider):
    """Placeholder provider. Wire in actual OpenAI client later."""

    name = "openai"

    def __init__(self, config: OpenAIConfig | None = None, **_: object) -> None:
        super().__init__()
        self.config = config or OpenAIConfig()

    def generate(self, prompt: str, **_: object) -> ModelResponse:
        # TODO: integrate actual OpenAI client
        return ModelResponse(text=f"[openai mock::{self.config.model}] {prompt}")
