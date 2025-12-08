"""
Normalizes model outputs or tool responses.
"""
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class ParsedResponse:
    """Structured output from Raw model/tool responses."""

    content: str
    metadata: Dict[str, Any]


class ResponseParser:
    """Placeholder parser; extend with Pydantic or JSON schema validation later."""

    def parse(self, raw: str | dict) -> ParsedResponse:
        if isinstance(raw, dict):
            content = raw.get("content", "")
            metadata = raw
        else:
            content = raw
            metadata = {}
        return ParsedResponse(content=content, metadata=metadata)
