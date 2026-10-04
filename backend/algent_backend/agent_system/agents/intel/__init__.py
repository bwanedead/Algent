"""
The intel desk — a domain-agnostic watch recipe: emergent theaters, their heat, and briefs.

Heat (``heat.py``) finds what is boiling in the radar's history without being told where to look;
briefs (``brief.py``) turn a hot theater into intelligence, commissioning research that also feeds
the Pulses; ``render.py`` makes both readable. Vision: docs/vision/ohmega-intelligence-engine.md.
"""

from .contracts import Brief, Theater, TheaterHeat

__all__ = ["Brief", "Theater", "TheaterHeat"]
