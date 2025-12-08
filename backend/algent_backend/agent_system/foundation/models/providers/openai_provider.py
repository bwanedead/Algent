"""
OpenAI provider stub.

This module intentionally avoids importing the SDK to keep dependencies optional.
"""
from .base_provider import BaseModelProvider, ModelResponse


class OpenAIProvider(BaseModelProvider):
    """Placeholder provider. Wire in actual API calls later."""

    name = "openai"

    def generate(self, prompt: str, **_: object) -> ModelResponse:
        # TODO: integrate actual OpenAI client
        return ModelResponse(text=f"[openai mock] {prompt}")
