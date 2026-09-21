"""
The ``newsroom`` CLI category — run the story pipeline, or any contiguous slice of it.

One command (``run``) over a declared stage ladder, rather than a command per stage:
see ``pipeline.STAGES``. Registered into the unified entry point by ``cli/__main__``.
"""

from __future__ import annotations

from . import briefing, corpus, insight, pause, pipeline, radar, resume, steer

COMMANDS = (pipeline, radar, resume, pause, steer, corpus, briefing, insight)
