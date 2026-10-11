"""Feed registry — one module per feed, each exposing ``FEED``. Adding a feed is a module here plus one line below."""

from __future__ import annotations

from ..contracts import Feed
from . import adsb, ais, firms, ioda, usgs

FEEDS: dict[str, Feed] = {f.name: f for f in (ioda.FEED, usgs.FEED, adsb.FEED, firms.FEED, ais.FEED)}

#: Feeds the timer runner fetches (AIS is a service).
TIMER_FEEDS: tuple[str, ...] = ("ioda", "usgs", "adsb", "firms")
