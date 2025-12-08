"""
xAI provider stub (e.g., Grok models).
"""
from dataclasses import dataclass, field
import os

from .base_provider import BaseModelProvider, ModelResponse
from algent_backend.config import get_provider_api_key


@dataclass
class XAIConfig:
    """Configuration for xAI models."""

    api_key: str | None = field(default_factory=lambda: get_provider_api_key("xai"))
    base_url: str = field(default_factory=lambda: os.getenv("XAI_BASE_URL", "https://api.x.ai/v1"))
    model: str = field(default_factory=lambda: os.getenv("XAI_MODEL", "grok-beta"))


class XAIProvider(BaseModelProvider):
    """Placeholder for xAI integration."""

    name = "xai"

    def __init__(self, config: XAIConfig | None = None, **_: object) -> None:
        super().__init__()
        self.config = config or XAIConfig()

    def generate(self, prompt: str, **_: object) -> ModelResponse:
        # TODO: integrate xAI client
        return ModelResponse(text=f"[xai mock::{self.config.model}] {prompt}")
