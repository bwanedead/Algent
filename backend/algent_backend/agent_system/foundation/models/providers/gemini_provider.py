"""
Google Gemini provider stub.
"""
from dataclasses import dataclass, field
import os

from .base_provider import BaseModelProvider, ModelResponse
from algent_backend.config import get_provider_api_key


@dataclass
class GeminiConfig:
    """Configuration for Gemini models."""

    api_key: str | None = field(default_factory=lambda: get_provider_api_key("gemini") or os.getenv("GOOGLE_API_KEY"))
    base_url: str = field(default_factory=lambda: os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"))
    model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-1.5-pro"))


class GeminiProvider(BaseModelProvider):
    """Placeholder for Gemini integration."""

    name = "gemini"

    def __init__(self, config: GeminiConfig | None = None, **_: object) -> None:
        super().__init__()
        self.config = config or GeminiConfig()

    def generate(self, prompt: str, **_: object) -> ModelResponse:
        # TODO: integrate Gemini SDK or REST client
        return ModelResponse(text=f"[gemini mock::{self.config.model}] {prompt}")
