"""
The crawler's network seam: honest user-agent, per-domain pacing, robots.txt, conditional GETs.

Feeds, sitemaps and robots.txt are fetched here, identifying as ``USER_AGENT``. Page text is read by the
shared free reader (``fetch_content._fetch(..., allow_paid_fallback=False)``) — one extraction ladder for
the whole repo — but only AFTER ``allowed`` has cleared the URL against the site's robots.txt and after
``pace`` has spaced it from the last hit on that host. Tests inject ``http`` / ``read_page`` / ``sleep``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

USER_AGENT = "OhmegaLibraryBot/0.1 (Algent research index; honours robots.txt; low volume)"
TIMEOUT_S = 30.0
PACE_S = 2.0                  # minimum gap between two requests to one host
MAX_CRAWL_DELAY_S = 10.0      # a site's Crawl-delay is honoured up to this
MAX_BODY_BYTES = 5_000_000


class NetError(RuntimeError):
    """A request failed at network level (the message names the cause)."""


@dataclass
class Response:
    status: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


def default_http(url: str, headers: dict[str, str]) -> Response:
    import httpx

    try:
        r = httpx.get(url, headers=headers, timeout=TIMEOUT_S, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise NetError(f"{type(exc).__name__}: {str(exc)[:100]}") from exc
    return Response(r.status_code, r.content[:MAX_BODY_BYTES], {k.lower(): v for k, v in r.headers.items()})


def default_read_page(url: str) -> dict[str, Any]:
    from algent_backend.agent_system.tools.sourcing.depth.fetch_content import _fetch

    return _fetch(url, allow_paid_fallback=False)


class Net:
    def __init__(self, *, http: Callable[[str, dict[str, str]], Response] = default_http,
                 read_page: Callable[[str], dict[str, Any]] = default_read_page,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 pace_s: float = PACE_S) -> None:
        self._http, self._read_page, self._sleep, self._clock = http, read_page, sleep, clock
        self.pace_s = pace_s
        self._last: dict[str, float] = {}
        self._robots: dict[str, tuple[RobotFileParser, str]] = {}

    def pace(self, host: str, extra: float = 0.0) -> None:
        wait = max(self.pace_s, extra) - (self._clock() - self._last.get(host, float("-inf")))
        if wait > 0:
            self._sleep(wait)
        self._last[host] = self._clock()

    def get(self, url: str, *, etag: str = "", last_modified: str = "") -> Response:
        """Paced GET; sends validators when given so an unchanged feed costs a 304."""
        headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*;q=0.8"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        self.pace(urlsplit(url).netloc)
        return self._http(url, headers)

    def _robots_for(self, url: str) -> tuple[RobotFileParser, str]:
        """(parser, reason-if-closed). Mirrors urllib: 401/403 closes the site, other 4xx opens it."""
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            rp, reason = RobotFileParser(), ""
            rp.modified()
            try:
                resp = self.get(f"{origin}/robots.txt")
            except NetError as exc:
                rp.disallow_all, reason = True, f"robots.txt unreachable ({exc})"
            else:
                if resp.status in (401, 403):
                    rp.disallow_all, reason = True, f"robots.txt forbids access (HTTP {resp.status})"
                elif resp.status >= 500:
                    rp.disallow_all, reason = True, f"robots.txt unavailable (HTTP {resp.status}); skipping this run"
                elif resp.status == 200:
                    rp.parse(resp.body.decode("utf-8", "replace").splitlines())
                else:
                    rp.allow_all = True                              # 404 and friends: no rules published
            self._robots[origin] = (rp, reason)
        return self._robots[origin]

    def allowed(self, url: str) -> tuple[bool, str]:
        rp, reason = self._robots_for(url)
        if not rp.can_fetch(USER_AGENT, url):
            return False, reason or "disallowed by robots.txt"
        return True, ""

    def crawl_delay(self, url: str) -> float:
        delay = self._robots_for(url)[0].crawl_delay(USER_AGENT)
        return min(float(delay), MAX_CRAWL_DELAY_S) if delay else 0.0

    def read_page(self, url: str) -> dict[str, Any]:
        self.pace(urlsplit(url).netloc, extra=self.crawl_delay(url))
        return self._read_page(url)
