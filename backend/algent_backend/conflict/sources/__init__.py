"""Conflict sources: each module turns one provider's response into ``ConflictEvent`` rows (``parse``) and fetches it (``fetch``)."""

from __future__ import annotations

import os

from algent_backend.polite_http import SourceUnavailable


class NeedsKey(SourceUnavailable):
    """The source is built and ready but holds no key; the message says exactly how to get one."""


def env(name: str) -> str:
    return os.environ.get(name, "").strip()


def country_iso(name: str) -> str:
    """ISO2 for a country name a provider wrote, or "" (never guessed)."""
    try:
        from algent_backend.actors import registry

        return registry.resolve(name) or ""
    except Exception:  # noqa: BLE001 - a missing seed must not stop a collector
        return ""
