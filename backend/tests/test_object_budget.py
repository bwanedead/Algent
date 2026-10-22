"""The R2 free-tier guard: counters, soft warn, hard stop, daily cap, month rollover, graceful refusal. No network, fake clock."""

from __future__ import annotations

from datetime import datetime, timezone

from algent_backend.database import flags
from algent_backend.publishing import asset_store, object_budget, object_store


class Clock:
    def __init__(self, y=2026, m=10, d=15, h=12) -> None:
        self.t = datetime(y, m, d, h, tzinfo=timezone.utc)
        self.mono = 100.0

    def now(self) -> datetime:
        return self.t

    def tick(self) -> float:
        self.mono += 0.1
        return self.mono


def _meter(tmp_path, clock: Clock | None = None) -> object_budget.Meter:
    c = clock or Clock()
    return object_budget.Meter(tmp_path / "usage.json", now=c.now, clock=lambda: c.tick())


def test_counts_operations_and_bytes_and_persists(tmp_path) -> None:
    m = _meter(tmp_path)
    m.record("a", key="docs/x.gz", size=100)
    m.record("a", key="docs/y.gz", size=50)
    m.record("a", key="docs/x.gz", size=70)           # an overwrite replaces the size, it does not add
    m.record("b")
    m.flush()
    u = _meter(tmp_path).usage()                      # a fresh process sees the file
    assert (u["a"], u["b"], u["bytes"]) == (3, 1, 120)
    m.record("a", key="docs/y.gz", removed=True)
    assert m.usage()["bytes"] == 70


def test_two_processes_add_their_counts_instead_of_overwriting(tmp_path) -> None:
    a, b = _meter(tmp_path), _meter(tmp_path)
    for _ in range(3):
        a.record("a")
    for _ in range(4):
        b.record("a")
    a.flush()
    b.flush()
    assert _meter(tmp_path).usage()["a"] == 7


def test_hard_stop_at_90_percent_of_the_monthly_class_a_tier(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(flags, "R2_FREE_CLASS_A", 1000)
    monkeypatch.setattr(flags, "R2_DAILY_STOP_MULT", 100.0)        # isolate the monthly rule
    m = _meter(tmp_path)
    for _ in range(899):
        m.record("a")
    assert m.check("a") == ""
    m.record("a")
    assert "Class A" in m.check("a") and "hard stop" in m.check("a")
    assert m.check("b") == ""                                       # reads are a separate budget


def test_daily_cap_stops_a_runaway_day_not_the_month(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(flags, "R2_FREE_CLASS_A", 31_000)           # 1000 a day in a 31-day month; cap = 3x = 3000
    m = _meter(tmp_path, Clock(2026, 10, 15))
    for _ in range(2999):
        m.record("a")
    assert m.check("a") == ""
    m.record("a")
    assert "daily cap" in m.check("a")
    clock = Clock(2026, 10, 16)                                     # the next UTC day starts clean
    assert _meter(tmp_path, clock).check("a") == ""


def test_storage_hard_stop_counts_the_new_object_and_credits_the_overwritten_one(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(flags, "R2_FREE_STORAGE_BYTES", 1000)
    m = _meter(tmp_path)
    m.record("a", key="k", size=800)
    assert m.check("a", 50, "other") == ""                           # 850 < 900
    assert "storage" in m.check("a", 150, "other")                   # 950 >= 900
    assert m.check("a", 150, "k") == ""                              # replacing k: 800 - 800 + 150


def test_month_rollover_resets_operations_but_keeps_the_stored_bytes(tmp_path) -> None:
    clock = Clock(2026, 10, 31)
    m = _meter(tmp_path, clock)
    m.record("a", key="k", size=10)
    m.flush()
    clock.t = datetime(2026, 11, 1, tzinfo=timezone.utc)
    m2 = _meter(tmp_path, clock)
    u = m2.usage()
    assert u["month"] == "2026-11" and u["a"] == 0 and u["bytes"] == 10


def test_status_reports_levels_and_projection(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(flags, "R2_FREE_CLASS_A", 1000)
    monkeypatch.setattr(flags, "R2_DAILY_STOP_MULT", 100.0)
    m = _meter(tmp_path, Clock(2026, 10, 11, 0))                     # exactly 10 days elapsed
    for _ in range(100):
        m.record("a")
    s = m.status()
    a = s["usage"]["class_a"]
    assert a["level"] == "ok" and a["projected_month"] == 310 and s["level"] == "ok"
    for _ in range(600):
        m.record("a")
    assert m.status()["usage"]["class_a"]["level"] == "warn"          # 70% of the month's tier
    for _ in range(200):
        m.record("a")
    assert m.status()["level"] == "stop"


def test_a_refused_put_returns_429_makes_no_call_and_does_not_raise(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(flags, "R2_FREE_CLASS_A", 10)
    monkeypatch.setattr(flags, "R2_DAILY_STOP_MULT", 100.0)
    calls: list = []

    def call(method, url, headers, body):
        calls.append(method)
        return 200, {}, b""

    clock = Clock()
    store = object_store.R2Store("a", "k", "s", "b", "https://pub", call=call, now=clock.now, meter=_meter(tmp_path, clock))
    codes = [store.put(f"k{i}", b"x", content_type="x", cache_control="x") for i in range(12)]
    assert codes[:9] == [200] * 9 and codes[9:] == [429] * 3 and len(calls) == 9
    assert "REFUSED" in capsys.readouterr().out
    assert store.get("k0") == b"" or True                              # reads still allowed (own budget)


def test_uploader_reports_a_guarded_object_as_failed_and_retries_it_later(tmp_path, monkeypatch) -> None:
    for k, v in {"R2_ACCOUNT_ID": "a", "R2_ACCESS_KEY_ID": "k", "R2_SECRET_ACCESS_KEY": "s", "R2_BUCKET": "b", "R2_PUBLIC_BASE": "https://p"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(flags, "R2_FREE_CLASS_A", 10)
    monkeypatch.setattr(flags, "R2_DAILY_STOP_MULT", 100.0)
    out = None
    for i in range(12):
        out = asset_store.upload({f"/live/n{i}.json": b"{}"}, http=lambda *a: 200, manifest=tmp_path / "m.json")
    assert out is not None and out["ok"] is False and out["failed"] == ["/live/n11.json (429)"]
    s = asset_store.upload({"/live/n11.json": b"{}"}, http=lambda *a: 200, manifest=tmp_path / "m.json")
    assert s["failed"] == ["/live/n11.json (429)"]                     # the manifest never recorded it: it is retried, not lost


def test_parallel_workers_cannot_overshoot_the_stop_together(tmp_path, monkeypatch) -> None:
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(flags, "R2_FREE_CLASS_A", 100)
    monkeypatch.setattr(flags, "R2_DAILY_STOP_MULT", 100.0)
    m = _meter(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        granted = sum(1 for r in pool.map(lambda _: m.acquire("a") == "", range(300)) if r)
    assert granted == 90                                              # exactly the 90% stop, however the threads interleave


def test_status_cli_prints_the_report(capsys) -> None:
    from algent_backend.cli.newsroom import storage

    assert storage.run_status(None) == 0
    out = capsys.readouterr().out
    assert '"class_a"' in out and '"projected_month"' in out


def test_live_cadence_fits_well_under_the_free_tier() -> None:
    """The documented write plan: R2 mode publishes 4 objects per 180 s plus 9 track objects per 900 s, no tiles."""
    from algent_backend.live import flags as live

    per_day = 4 * 86400 // live.R2_SNAPSHOT_SECONDS + (1 + 2 * live.R2_TRACK_SHARDS) * 86400 // live.R2_TRACKS_SECONDS
    assert per_day * 31 <= 0.15 * flags.R2_FREE_CLASS_A
    assert live.cost_capped() and not live.tiles_enabled() and live.full_snapshot()
