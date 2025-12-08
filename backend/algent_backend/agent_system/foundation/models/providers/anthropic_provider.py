"""
Anthropic provider stub.
"""
from dataclasses import dataclass, field
import os

from .base_provider import BaseModelProvider, ModelResponse
from algent_backend.config import get_provider_api_key


@dataclass
class AnthropicConfig:
    """Configuration for Anthropic Claude models."""

    api_key: str | None = field(default_factory=lambda: get_provider_api_key("anthropic"))
    base_url: str = field(default_factory=lambda: os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com"))
    model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet"))


class AnthropicProvider(BaseModelProvider):
    """Placeholder for Anthropic integration."""

    name = "anthropic"

    def __init__(self, config: AnthropicConfig | None = None, **_: object) -> None:
        super().__init__()
        self.config = config or AnthropicConfig()

    def generate(self, prompt: str, **_: object) -> ModelResponse:
        # TODO: integrate Anthropic SDK
        return ModelResponse(text=f"[anthropic mock::{self.config.model}] {prompt}")
