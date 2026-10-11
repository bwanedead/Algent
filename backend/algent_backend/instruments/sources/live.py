"""
``live`` provider — a deliberate no-op. The ``live_*`` series are written by the live collectors themselves
(``algent_backend/live``: timer jobs and the AIS service append completed days), so a catalog-wide
``instruments fetch`` has nothing to pull for them and must not report them as failed.
"""

from __future__ import annotations

from ..contracts import Observation, Series


def fetch(series: Series, since) -> list[Observation]:
    return []
