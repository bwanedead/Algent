"""
Live contracts — the one vocabulary every collector, the store, the publisher and the desk share.

A feed is a ``Feed``: a name, where its data is publicly shown, optionally the free key it needs, and a
``fetch(ctx) -> FeedResult``. A result is ``LiveEvent`` rows (things happening now: an outage, a quake, a cluster
of aircraft, a fire) and ``Stat`` readings (numbers for ``live_*`` instrument series). Nothing here fetches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "notable", "major"]
Kind = Literal["outage", "quake", "aircraft", "fire"]


class LiveEvent(BaseModel):
    id: str                                   # stable per real-world thing, so a re-fetch updates rather than duplicates
    feed: str
    kind: Kind
    title: str                                # one plain line: "Internet outage in Iran"
    detail: str = ""                          # the plain explanation a reader gets in the popover, caveats included
    lat: float | None = None
    lon: float | None = None
    countries: list[str] = Field(default_factory=list)   # names as the desk writes them (matched against theaters)
    severity: Severity = "info"
    start: str = ""                           # ISO-8601 UTC
    end: str | None = None                    # None = still going / a snapshot of now
    source_url: str = ""                      # the public dashboard or event page a reader can open
    source: str = ""                          # who publishes it ("IODA, Georgia Tech")
    tags: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class Stat(BaseModel):
    """One reading for a ``live_*`` instrument series. ``mode='max'`` keeps the day's highest sample (aircraft
    seen at once), ``'set'`` replaces the running value (a count the collector keeps itself)."""

    series_id: str
    value: float
    mode: Literal["max", "set"] = "max"


class FeedResult(BaseModel):
    events: list[LiveEvent] = Field(default_factory=list)
    stats: list[Stat] = Field(default_factory=list)
    note: str = ""


class NeedsKey(RuntimeError):
    """The feed is fine but we hold no key for it; the message says exactly how to get one."""


@dataclass
class Ctx:
    get: Callable[..., str]                   # polite_http.get-shaped; tests pass a fake
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    key: str = ""


@dataclass(frozen=True)
class Feed:
    name: str
    label: str
    source: str
    source_url: str
    fetch: Callable[[Ctx], FeedResult]
    key_env: str = ""                         # "" = keyless
    signup_url: str = ""

    def needs(self) -> str:
        return f"needs {self.key_env} (free registration at {self.signup_url})"


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def from_epoch(seconds: float) -> str:
    return iso(datetime.fromtimestamp(seconds, tz=timezone.utc))
