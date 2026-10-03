"""
Structured output over a STREAMING OpenAI client, with the strict schema the provider requires.

LangChain's ``ChatOpenAI`` sends a pydantic structured request two different ways. Non-streaming it
hands the class to the SDK's ``responses.parse``, which runs ``to_strict_json_schema`` (adds
``additionalProperties: false`` to every object, lists every property as required, resolves
``$defs``). Streaming it cannot use ``parse``, so it sends ``schema.model_json_schema()`` with
``strict: true`` and NO strict transformation. Any model with a nested object or a defaulted field
then 400s: ``'additionalProperties' is required to be supplied and to be false`` — which killed
every intel-daily section and the article draft's structured step the day streaming was enabled.

This module closes that gap at our layer: for a pydantic class it builds the same strict schema the
parse path sends, binds it as the request's ``response_format``, and validates the reply back into
the class itself. Anything it cannot handle (non-pydantic schemas, an SDK without the helper)
falls back to LangChain's own path, unchanged.
"""

from __future__ import annotations

import inspect
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableLambda


def strict_response_format(schema: type) -> dict[str, Any]:
    """The ``response_format`` dict OpenAI's strict mode accepts for a pydantic class."""
    from openai.lib._pydantic import to_strict_json_schema

    return {
        "name": schema.__name__,
        "description": inspect.getdoc(schema) or "",
        "schema": to_strict_json_schema(schema),
        "strict": True,
    }


def _is_pydantic_class(schema: Any) -> bool:
    from pydantic import BaseModel

    return inspect.isclass(schema) and issubclass(schema, BaseModel)


def _parse_reply(schema: type, ai_msg: AIMessage) -> dict[str, Any]:
    """Shape a raw reply like LangChain's ``include_raw=True``: raw message plus the parsed object.

    A refusal (or an empty reply) parses to ``None``, which the gate's structured retry treats as
    "no object" and asks again; prose raises pydantic's ``Invalid JSON`` and is retried the same way.
    """
    text = str(ai_msg.text).strip()
    parsed = schema.model_validate_json(text) if text else None
    return {"raw": ai_msg, "parsed": parsed, "parsing_error": None}


def structured_over_stream(client: Any, schema: Any, kwargs: dict[str, Any]) -> Runnable | None:
    """A strict-schema structured runnable over ``client``, or ``None`` to use LangChain's default.

    Only pydantic classes on an OpenAI-shaped client (one that exposes ``bind``) are rewritten; a
    caller that pinned a non-default ``method`` keeps LangChain's behaviour.
    """
    if not _is_pydantic_class(schema) or kwargs.get("method", "json_schema") != "json_schema":
        return None
    try:
        response_format = strict_response_format(schema)
    except ImportError:  # the SDK helper moved; the default path still works for simple models
        return None
    bound = client.bind(response_format=response_format)
    return bound | RunnableLambda(lambda msg: _parse_reply(schema, msg))
