"""
GIE ALSI — EU LNG terminals: send-out (GWh/day) and how full the tanks are (% of technical capacity). Same free key and
response shape as AGSI (``ALGENT_AGSI_KEY``; one GIE registration covers both), different host. Series params: ``type`` (``eu``
aggregate) and ``field`` (``sendOut``, ``full``). The response shape follows GIE's published schema and is unverified against a
live key. Credit GIE ALSI wherever it is shown.
"""

from __future__ import annotations

from datetime import date

from ..contracts import Observation, Series
from .agsi import fetch_pages

URL = "https://alsi.gie.eu/api"


def fetch(series: Series, since: date | None) -> list[Observation]:
    return fetch_pages(URL, series, since)
