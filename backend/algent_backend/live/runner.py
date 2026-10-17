"""
Live runner — one timer run of the chosen feeds: fetch -> events snapshot + stats -> status -> publish.

Each feed is isolated (a feed that is down, or needs a key we do not hold, is recorded and never stops the others).
A failed fetch keeps the previous snapshot rather than blanking the map. Publishing to the site database is
best-effort and only when ``DATABASE_URL`` is set. Cheap by design: a handful of GETs per run, no model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from algent_backend import polite_http

from . import energy, headlines, memory, snapshots
from . import publish as live_publish
from . import store
from .contracts import Ctx, NeedsKey
from .feeds import FEEDS, TIMER_FEEDS
from .feeds.ais import FEED as AIS


def _key(feed) -> str:
    import os

    return os.environ.get(feed.key_env, "") if feed.key_env else ""


def run(names: list[str] | None = None, *, get: Callable[..., str] | None = None, now: datetime | None = None,
        publish: bool = True, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    names = names or list(TIMER_FEEDS)
    for n in names:
        if n not in FEEDS or n not in TIMER_FEEDS:
            raise KeyError(f"unknown timer feed {n!r}; known: {', '.join(TIMER_FEEDS)} (ais is a service: `newsroom live ais`)")
    polite_http.clear_memo()
    rows: list[dict[str, Any]] = []
    fresh: dict[str, list] = {}
    stats = []
    docs: dict[str, dict] = {}
    stamp = now.isoformat(timespec="seconds")
    for n in names:
        feed = FEEDS[n]
        store.record_status(n, last_attempt=stamp)
        try:
            res = feed.fetch(Ctx(get=get or polite_http.get, now=now, key=_key(feed), lines=None if get else polite_http.stream_lines))
        except NeedsKey as exc:
            store.record_status(n, needs=str(exc), error="")
            rows.append({"feed": n, "status": "needs_key", "note": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001 - one feed down must not stop the rest
            msg = f"{type(exc).__name__}: {str(exc)[:160]}"
            store.record_status(n, error=msg, needs="")
            rows.append({"feed": n, "status": "error", "note": msg})
            continue
        store.write_events(n, res.events)
        memory.record_events(n, res.events, now.timestamp())             # live memory: outage / quake counts of the hour
        if "fires" in res.docs:
            memory.record_fires(res.docs["fires"], now.timestamp())      # ... and the fire picture
        fresh[n] = res.events
        stats += res.stats
        docs.update(res.docs)
        if "fires" in res.docs:
            f = res.docs["fires"]
            store.write_doc("fires_meta", {k: f[k] for k in ("as_of", "detections", "occupied")})
        store.record_status(n, last_ok=stamp, error="", needs="", n_events=len(res.events), note=res.note)
        rows.append({"feed": n, "status": "ok", "events": len(res.events), "stats": len(res.stats), "note": res.note})
    tally = store.apply_stats(stats, now.date()) if stats or store.running() else {}
    out: dict[str, Any] = {"as_of": stamp, "feeds": rows, "stats": tally}
    if publish and (docs or fresh):
        if (en := energy.build(now)) is not None:
            docs["energy"] = en
        docs["summary"] = headlines.build(now)
        out["snapshots"] = snapshots.publish(docs, local=("summary",))
    if publish and fresh:
        out["publish"] = live_publish.publish(fresh, today=now.date(), connect=connect)
        if out["publish"].get("db"):
            out["world"] = live_publish.publish_world(connect=connect)
    if publish:                           # live memory: settle finished hours into baselines, anomalies and daily rollups (a no-op until an hour has ended)
        from .memory import tick as memory_tick

        out["memory"] = memory_tick.tick(now.timestamp(), connect=connect)
        from algent_backend.maritime import publish as maritime_publish

        out["maritime"] = maritime_publish.run(connect=connect)          # AIS behaviour events the stream service wrote: site table + ledger link
    return out


def doctor_rows() -> list[dict[str, Any]]:
    """Per feed (timer feeds and AIS): key situation and last success, for ``newsroom doctor`` and ``live status``."""
    status, rows = store.read_status(), []
    for name, feed in FEEDS.items():
        st = status.get(name, {})
        rows.append({"feed": name, "label": feed.label, "key_env": feed.key_env, "keyless": not feed.key_env,
                     "key_set": bool(_key(feed)) if feed.key_env else True, "needs": feed.needs() if feed.key_env and not _key(feed) else "",
                     "last_ok": st.get("last_ok", ""), "last_attempt": st.get("last_attempt", ""), "error": st.get("error", ""),
                     "service": feed is AIS, "note": st.get("note", "")})
    return rows
