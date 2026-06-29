"""Gauntlet — the orchestrator that runs review -> enrich -> merge -> re-review as one round."""

from __future__ import annotations

from .contracts import GauntletReport

__all__ = ["GauntletReport"]
