"""
The ``live_*`` instrument series our own collectors produce (merged into ``instruments.catalog.CATALOG``; lives in this package so the catalog never imports a module that imports it back).

They have no remote fetcher: the ``live`` provider is a no-op because the collectors (timer jobs and the AIS service)
append COMPLETED days directly (``live/store.py``). Daily cadence, one-day lag (a day closes at UTC midnight).
Ship counts carry the ``chokepoint`` tag so the numbers panel shows them beside the IMF PortWatch reference
series; aircraft and fire counts are context for the section writers.
"""

from __future__ import annotations

from algent_backend.live.regions import FIRE_BOXES, GATES, REGIONS

from .contracts import Series

_LICENCE = "Ohmega's own count from a public live feed; attribute Ohmega and the feed"
_AIS_URL = "https://aisstream.io/"
_ADSB_URL = "https://adsb.lol/"
_FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/map/"


def ais_ids(slug: str) -> tuple[str, str]:
    return f"live_ais_{slug}_transits", f"live_ais_{slug}_tanker_transits"


def mil_ids(slug: str) -> tuple[str, str]:
    return f"live_mil_{slug}", f"live_mil_{slug}_support"


def fire_id(slug: str) -> str:
    return f"live_fire_{slug}"


_PLAIN_AIS = ("Ships that crossed {label} on a UTC day, counted by Ohmega from ships' public position broadcasts (AIS). "
              "Coverage is partial, so read the trend, not the exact number.")
_PLAIN_AIS_TANKER = "Oil and fuel tankers that crossed {label} on a UTC day, counted from ships' public position broadcasts (AIS). A drop can mean fuel flows are being held up."
_PLAIN_MIL = ("The most military aircraft seen in the air over {label} at one moment that day, from public flight-tracker "
              "broadcasts. Surges can precede or accompany a crisis; aircraft that switch tracking off are not counted.")
_PLAIN_SUPPORT = ("The most aerial refuelling tankers and surveillance aircraft seen over {label} at once that day. "
                  "Their presence suggests sustained operations, because strike aircraft depend on them.")
_PLAIN_FIRE = ("Satellite-detected heat hotspots in {label} that day (NASA FIRMS). Fires from strikes or shelling show up "
               "here, but so do farm and wildfire, so it is a clue and not proof.")


def _series() -> list[Series]:
    common = dict(frequency="daily", cadence="daily", lag_days=1, fetcher="live", licence=_LICENCE, public_display=True)
    out: list[Series] = []
    for g in GATES:
        total, tanker = ais_ids(g.slug)
        tags = ["chokepoint", "shipping", "live", *g.tags]
        src = dict(source="Ohmega AIS count (aisstream.io)", source_url=_AIS_URL, unit="ships/day")
        out += [Series(id=total, name=f"{g.label} — ships crossing (Ohmega AIS count)", tags=tags,
                       plain=_PLAIN_AIS.format(label=g.label), **src, **common),
                Series(id=tanker, name=f"{g.label} — tankers crossing (Ohmega AIS count)", tags=[*tags, "oil", "energy"],
                       plain=_PLAIN_AIS_TANKER.format(label=g.label), **src, **common)]
    for r in REGIONS:
        total, support = mil_ids(r.slug)
        tags = ["aircraft", "military", "live", *r.tags]
        src = dict(source="adsb.lol (ADS-B, Ohmega daily maximum)", source_url=_ADSB_URL, unit="aircraft")
        out += [Series(id=total, name=f"{r.label} — military aircraft in the air at once", tags=tags,
                       plain=_PLAIN_MIL.format(label=r.label), **src, **common),
                Series(id=support, name=f"{r.label} — tankers and surveillance aircraft", tags=[*tags, "isr"],
                       plain=_PLAIN_SUPPORT.format(label=r.label), **src, **common)]
    for b in FIRE_BOXES:
        out.append(Series(id=fire_id(b.slug), name=f"{b.label} — satellite heat hotspots per day", tags=["fires", "live", *b.tags],
                          source="NASA FIRMS (VIIRS)", source_url=_FIRMS_URL, unit="hotspots",
                          plain=_PLAIN_FIRE.format(label=b.label), **common))
    return out


LIVE_SERIES: list[Series] = _series()
