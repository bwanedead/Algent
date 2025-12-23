"""
Vocabulary packs for GraphOS.
"""
from __future__ import annotations

from typing import Iterable

from ..registry import VocabularyRegistry
from . import algo_lab


def register_all(registry: VocabularyRegistry) -> None:
    for pack in (algo_lab,):
        pack.register(registry)
