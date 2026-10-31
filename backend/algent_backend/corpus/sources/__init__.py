"""
The source adapters, one module per registered product (or small family of them). Order is fixed and only matters for readability of the
report: the result of a build does not depend on it (``link.py`` resolves names after everything is read).

Adding a source: write ``sources/<name>.py`` with a ``SOURCE = Source(...)`` that reads the product's store through the product's own readers,
add the module name below, and add a fixture test. Nothing else changes.
"""

from __future__ import annotations

from importlib import import_module

from .base import Source

MODULES = ("actors", "dailies", "pulses", "profiles", "articles", "statements", "sanctions", "calendar", "geoledger", "maritime", "markets",
           "instruments", "ai_benchmarks", "conflict", "gnss", "elections")


def load(only: list[str] | None = None) -> list[Source]:
    """The adapters (all, or just the named ones), imported lazily so a missing optional dependency only costs its own source."""
    wanted = [m for m in MODULES if not only or m in only]
    return [import_module(f"{__name__}.{m}").SOURCE for m in wanted]
