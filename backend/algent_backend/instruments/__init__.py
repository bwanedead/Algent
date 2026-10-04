"""
Instruments — Ohmega's programmatic numbers layer (no model anywhere in this package).

Hard numbers that situations move — ship transits, prices, storage, yields — gathered from free
public sources into an append-only store and exposed as cited evidence. See
``docs/architecture/instruments.md``.

    from algent_backend.instruments import evidence_block, moves_board
"""

from .evidence import evidence_block, moves_board

__all__ = ["evidence_block", "moves_board"]
