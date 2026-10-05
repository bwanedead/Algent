"""
Polite HTTP for the free-data providers (instruments, actors) — one place for timeouts, retries, a browser UA and pacing.

Free public endpoints are a shared resource and some (Yahoo) reject obviously-scripted clients, so
every provider goes through ``get`` rather than building its own client. Failures raise
``SourceError`` naming the URL; the collector catches per series, so one provider being down never
stops the others. Responses are memoised per process because several series share one payload
(a chokepoint's total and tanker counts; the 2y and 10y Treasury yields) — ``clear_memo`` resets it.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
TIMEOUT_S = 60.0       # AGSI alone takes ~16s
RETRIES = 2            # attempts after the first
MIN_GAP_S = 0.25       # per-host pacing between requests

_memo: dict[tuple, str] = {}
_last_hit: dict[str, float] = {}


class SourceError(RuntimeError):
    """A provider call failed; the message names the URL."""


class SourceUnavailable(SourceError):
    """The source is reachable but we cannot read it (needs a key, blocked, retired) — not a bug."""


def clear_memo() -> None:
    _memo.clear()


def _pace(url: str) -> None:
    host = urlsplit(url).netloc
    wait = MIN_GAP_S - (time.monotonic() - _last_hit.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.monotonic()


def get(url: str, params: dict[str, Any] | None = None, *, headers: dict[str, str] | None = None) -> str:
    """GET ``url`` and return the body text; retries transient failures, memoised per process."""
    key = (url, tuple(sorted((params or {}).items())))
    if key in _memo:
        return _memo[key]
    hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*", **(headers or {})}
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        _pace(url)
        try:
            resp = httpx.get(url, params=params, headers=hdrs, timeout=TIMEOUT_S, follow_redirects=True)
        except httpx.HTTPError as exc:
            last = exc
        else:
            if resp.status_code in (401, 403):
                raise SourceUnavailable(f"{resp.url} -> HTTP {resp.status_code} (access denied)")
            if resp.status_code == 200:
                _memo[key] = resp.text
                return resp.text
            last = RuntimeError(f"HTTP {resp.status_code}")
        time.sleep(1.0 * (attempt + 1))
    raise SourceError(f"{url} failed after {RETRIES + 1} attempts: {last}")


def stream_lines(url: str, *, headers: dict[str, str] | None = None) -> Iterator[str]:
    """Yield a large text body line by line without holding it in memory (a big CSV); no retry or memo.
    Raises ``SourceError`` on a non-200 status or a transport failure before the first line."""
    hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*", **(headers or {})}
    _pace(url)
    try:
        with httpx.stream("GET", url, headers=hdrs, timeout=TIMEOUT_S, follow_redirects=True) as resp:
            if resp.status_code in (401, 403):
                raise SourceUnavailable(f"{resp.url} -> HTTP {resp.status_code} (access denied)")
            if resp.status_code != 200:
                raise SourceError(f"{url} -> HTTP {resp.status_code}")
            yield from resp.iter_lines()
    except httpx.HTTPError as exc:
        raise SourceError(f"{url} stream failed: {exc}") from exc
