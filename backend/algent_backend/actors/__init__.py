"""
Actors — Ohmega's power profiles of states (no model anywhere in this package).

What each power IS, as numbers: people, economy, trade, energy, military, leadership, gathered from
free open-licence sources into an append-only store and exposed as ``profile`` / ``compare`` /
``evidence_block``. The desk shows news; this shows the actors the news is about. See
``docs/architecture/actors.md``.

    from algent_backend.actors import profile, compare, evidence_block
"""

from .profile import compare, evidence_block, profile

__all__ = ["compare", "evidence_block", "profile"]
