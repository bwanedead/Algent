"""
The crawl: poll the registry's feeds and sitemaps, read what is new, index it. Bounded, polite, idempotent.

Phase 1 polls every feed once (conditional GET: a 304 costs nothing) and collects candidates per source.
Phase 2 reads pages round-robin across sources, so a small ``max_total`` still samples every outlet rather
than starving the last ones. A page is read only when it is new, or its feed stamp changed since last time
(then a changed text becomes revision n+1). Everything is capped per run (``per_source``, ``max_total``,
``max_seconds``) because the operator's laptop is weak, and there is no daemon: run it from cron or by hand.

Politeness: robots.txt is checked for every feed and page URL (a refusal parks the page and is reported),
requests to one host are spaced (``net.PACE_S``, or the site's Crawl-delay), feeds send ETag/Last-Modified,
the user-agent names the project. A feed that fails ``FEED_PARK_AFTER`` times in a row is parked for
``FEED_PARK_DAYS``; a page that fails ``PAGE_PARK_AFTER`` times is parked for good. Failures are recorded,
never raised: one dead source never stops the run. Free only (``allow_paid_fallback=False``), no model.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from . import store
from .net import Net, NetError
from .parse import Candidate, ParseError, parse_feed, parse_sitemap
from .sources import Source, all_sources

DEFAULT_PER_SOURCE = 6
DEFAULT_MAX_TOTAL = 120
DEFAULT_MAX_SECONDS = 900
FEED_PARK_AFTER = 4
FEED_PARK_DAYS = 7
PAGE_PARK_AFTER = 3
NOT_TEXT_SUFFIXES = (".xlsx", ".xls", ".csv", ".zip", ".pdf", ".doc", ".docx", ".mp3", ".mp4", ".jpg", ".png")
MIN_SUMMARY_WORDS = 15        # a feed blurb shorter than this is not worth indexing as the body


def _poll_feed(conn, net: Net, source: Source, feed, now: datetime, rep: dict[str, Any],
               validators: list[tuple[str, str, str]]) -> list[Candidate]:
    state = store.feed_state(conn, feed.url)
    if state and state["parked_until"] and state["parked_until"] > now.isoformat():
        rep["feeds_parked"] += 1
        return []

    def fail(reason: str) -> list[Candidate]:
        failures = (state["failures"] if state else 0) + 1
        park = (now + timedelta(days=FEED_PARK_DAYS)).isoformat() if failures >= FEED_PARK_AFTER else ""
        store.save_feed_state(conn, feed.url, source.id, failures=failures, last_error=reason[:200],
                              last_polled=now.isoformat(), parked_until=park)
        rep["feeds_failed"] += 1
        rep["errors"].append(f"{feed.url}: {reason[:120]}")
        return []

    ok, why = net.allowed(feed.url)
    if not ok:
        return fail(f"robots: {why}")
    try:
        resp = net.get(feed.url, etag=state["etag"] if state else "", last_modified=state["last_modified"] if state else "")
    except NetError as exc:
        return fail(str(exc))
    if resp.status == 304:
        store.save_feed_state(conn, feed.url, source.id, failures=0, last_polled=now.isoformat(), last_ok=now.isoformat(), parked_until="")
        rep["feeds_not_modified"] += 1
        return []
    if resp.status != 200:
        return fail(f"HTTP {resp.status}")
    try:
        candidates = (parse_sitemap if feed.type == "sitemap" else parse_feed)(resp.body)
    except ParseError as exc:
        return fail(str(exc))
    if not candidates:
        return fail("no entries")
    # Validators are held back until this source's backlog is read (see crawl): a 304 next run would hide it.
    validators.append((feed.url, resp.headers.get("etag", ""), resp.headers.get("last-modified", "")))
    store.save_feed_state(conn, feed.url, source.id, failures=0, last_error="", parked_until="", etag="", last_modified="",
                          last_polled=now.isoformat(), last_ok=now.isoformat())
    rep["feeds_ok"] += 1
    return candidates


def _pending(conn, source: Source, candidates: list[Candidate]) -> list[Candidate]:
    """New pages first (newest first), then pages whose feed stamp changed; known-and-unchanged are skipped."""
    seen: dict[str, Candidate] = {}
    for c in candidates:
        seen.setdefault(c.url, c)
    fresh, changed = [], []
    for c in seen.values():
        if c.url.lower().endswith(NOT_TEXT_SUFFIXES) or store.page_parked(conn, c.url):
            continue
        known = store.known_stamp(conn, c.url)
        if known is None:
            fresh.append(c)
        elif c.stamp and c.stamp != known:
            changed.append(c)
    newest = lambda c: c.published or ""            # noqa: E731
    return sorted(fresh, key=newest, reverse=True) + sorted(changed, key=newest, reverse=True)


def _index(conn, net: Net, source: Source, cand: Candidate, now: datetime) -> tuple[str, str]:
    """Read one page and store it. Returns (outcome, detail): new | revised | unchanged | failed | robots."""
    ok, why = net.allowed(cand.url)
    if not ok:
        transient = "unreachable" in why or "unavailable" in why        # a refusal parks the page; an outage only counts
        store.record_page_failure(conn, cand.url, source.id, f"robots: {why}", park_after=PAGE_PARK_AFTER, park_now=not transient)
        return "robots", why
    page: dict[str, Any] = {}
    error = ""
    try:
        page = net._read_page and net.read_page(cand.url)
    except Exception as exc:  # noqa: BLE001 - the reader raises on empty/blocked pages; that is a recorded failure
        error = f"{type(exc).__name__}: {str(exc)[:100]}"
    text, via = (page.get("content") or "").strip(), (page.get("via") or "page")
    if page.get("not_found") or page.get("quality") in ("blocked", "empty") or not text:
        text = ""
        error = error or page.get("error") or f"page read was {page.get('quality', 'empty')}"
    if not text and len(cand.summary.split()) >= MIN_SUMMARY_WORDS:
        text, via = cand.summary, "feed_summary"      # the page would not read; the feed's own blurb still finds it
    if not text:
        store.record_page_failure(conn, cand.url, source.id, error, park_after=PAGE_PARK_AFTER)
        return "failed", error
    meta_title = (page.get("meta") or {}).get("title", "")
    title = cand.title or meta_title or urlsplit(cand.url).path.rsplit("/", 1)[-1]
    doc = store.Doc(url=cand.url, source_id=source.id, domain=urlsplit(cand.url).netloc.lower(), kind=source.kind,
                    region=source.region, title=title, text=text, fetched_at=now.isoformat(timespec="seconds"),
                    published=cand.published, stamp=cand.stamp, via=via)
    return store.add_document(conn, doc), via


def _read_round_robin(conn, net: Net, wanted: list[Source], queues: dict[str, list[Candidate]],
                      reports: dict[str, dict[str, Any]], now: datetime, max_total: int, per_source: int,
                      started: float, max_seconds: float) -> int:
    """Phase 2: take one page per source per round until a cap or the clock stops it. Returns pages attempted."""
    taken = {sid: 0 for sid in queues}
    total = 0
    progressed = True
    while progressed and total < max_total and time.monotonic() - started < max_seconds:
        progressed = False
        for source in wanted:
            q = queues.get(source.id) or []
            if not q or taken[source.id] >= per_source or total >= max_total:
                continue
            cand = q.pop(0)
            taken[source.id] += 1
            total += 1
            progressed = True
            outcome, detail = _index(conn, net, source, cand, now)
            reports[source.id][outcome] += 1
            if outcome in ("failed", "robots"):
                reports[source.id]["errors"].append(f"{cand.url}: {detail[:100]}")
    return total


def crawl(source_ids: list[str] | None = None, *, max_total: int = DEFAULT_MAX_TOTAL, per_source: int = DEFAULT_PER_SOURCE,
          max_seconds: float = DEFAULT_MAX_SECONDS, net: Net | None = None, now: datetime | None = None,
          retain: bool = True) -> dict[str, Any]:
    """Run one bounded crawl. Returns a report: totals plus one row per source."""
    started = time.monotonic()
    net = net or Net()
    now = now or datetime.now(UTC)
    wanted = [s for s in all_sources() if (not source_ids or s.id in source_ids) and any(f.crawl for f in s.feeds)]
    conn = store.connect()
    reports: dict[str, dict[str, Any]] = {}
    queues: dict[str, list[Candidate]] = {}
    held: dict[str, list[tuple[str, str, str]]] = {}
    try:
        for source in wanted:                                    # phase 1: poll feeds
            rep = reports[source.id] = {"feeds_ok": 0, "feeds_failed": 0, "feeds_not_modified": 0, "feeds_parked": 0,
                                        "pending": 0, "new": 0, "revised": 0, "unchanged": 0, "failed": 0,
                                        "robots": 0, "errors": []}
            candidates: list[Candidate] = []
            held[source.id] = []
            for feed in source.feeds:
                if feed.crawl and time.monotonic() - started < max_seconds:
                    candidates += _poll_feed(conn, net, source, feed, now, rep, held[source.id])
            queues[source.id] = _pending(conn, source, candidates)
            rep["pending"] = len(queues[source.id])
        total = _read_round_robin(conn, net, wanted, queues, reports, now, max_total, per_source, started, max_seconds)
        for sid, items in held.items():                           # backlog drained -> next poll may be a cheap 304
            if not queues.get(sid):
                for url, etag, last_modified in items:
                    store.save_feed_state(conn, url, sid, etag=etag, last_modified=last_modified)
        removed = store.enforce_retention(conn, now=now) if retain else {}
    finally:
        conn.close()
    sums = {k: sum(r[k] for r in reports.values()) for k in ("new", "revised", "unchanged", "failed", "robots",
                                                              "feeds_ok", "feeds_failed", "feeds_not_modified", "feeds_parked")}
    return {"store": str(store.db_path()), "elapsed_s": round(time.monotonic() - started, 1), "pages_attempted": total,
            "totals": sums, "retention": removed, "sources": {sid: {k: v for k, v in r.items() if v or k == "pending"}
                                                               for sid, r in reports.items()}}
