"""
The ``newsroom`` CLI category — run the story pipeline, or any contiguous slice of it.

One command (``run``) over a declared stage ladder, rather than a command per stage:
see ``pipeline.STAGES``. Registered into the unified entry point by ``cli/__main__``.
"""

from __future__ import annotations

from . import (actors, ai_benchmarks, briefing, budget, calendar, corpus, db, doctor, flows, geo, insight, instruments, intel, library, live, maritime, markets, pause,
               pipeline, pulse, radar, reads, resume, runner, sanctions, satellite, schedule, statements, steer, storage, watchdog)

COMMANDS = (actors, pipeline, radar, resume, pause, steer, budget, corpus, briefing, insight, pulse, intel, instruments,
            statements, library, live, geo, reads, runner, doctor, watchdog, schedule, sanctions, calendar, maritime, markets, ai_benchmarks, flows, satellite, db, storage)
