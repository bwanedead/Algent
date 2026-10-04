"""Store append-only/revision behaviour and the moves math on synthetic series."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from algent_backend.instruments import moves, store
from algent_backend.instruments.catalog import get_series
from algent_backend.instruments.contracts import Observation


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_INSTRUMENTS_STORE", str(tmp_path / "istore"))


def ob(period, value):
    return Observation(series_id="s", period=period, value=value, fetched_at="2026-10-04T00:00:00+00:00", source_url="u")


def test_append_only_new_unchanged_and_revised():
    r1 = store.append("s", [ob("2026-01-01", 1.0), ob("2026-01-02", 2.0)])
    assert (r1.new, r1.revised, r1.unchanged) == (2, 0, 0)
    r2 = store.append("s", [ob("2026-01-02", 2.0), ob("2026-01-03", 3.0), ob("2026-01-01", 1.5)])
    assert (r2.new, r2.revised, r2.unchanged) == (1, 1, 1)
    lines = store.log("s")
    assert len(lines) == 4                                   # nothing rewritten, only appended
    assert [(o.period, o.revised) for o in lines][2:] == [("2026-01-01", True), ("2026-01-03", False)]
    assert {o.period: o.value for o in store.history("s")} == {
        "2026-01-01": 1.5, "2026-01-02": 2.0, "2026-01-03": 3.0}


def test_refetch_identical_writes_nothing():
    store.append("s", [ob("2026-01-01", 1.0)])
    size = store._path("s").stat().st_size
    store.append("s", [ob("2026-01-01", 1.0)])
    assert store._path("s").stat().st_size == size


def test_history_orders_by_period_with_month_periods():
    store.append("s", [ob("2026-03", 3.0), ob("2026-01", 1.0), ob("2026-02", 2.0)])
    assert [o.period for o in store.history("s")] == ["2026-01", "2026-02", "2026-03"]


def series(values, start=date(2025, 1, 1)):
    return [(start + timedelta(days=i), v) for i, v in enumerate(values)]


def test_changes_and_horizons():
    pts = series([float(i + 1) for i in range(400)])
    m = moves.compute(pts, today=pts[-1][0])
    assert m["latest"]["value"] == 400.0
    assert m["changes"]["prev"]["abs"] == 1.0
    assert m["changes"]["7d"]["from_value"] == 393.0 and m["changes"]["30d"]["from_value"] == 370.0
    assert m["changes"]["1y"]["from_value"] == 35.0
    assert m["percentile_1y"] > 99 and m["new_high"] == "1y"


def test_short_history_omits_unreachable_horizons():
    m = moves.compute(series([1.0, 2.0, 3.0]), today=date(2025, 1, 3))
    assert set(m["changes"]) == {"prev"} and m["unusual"] is False      # too few obs for any z


def test_monthly_series_skips_short_horizons():
    pts = [(date(2025 + i // 12, 1 + i % 12, 1), 2.0 + i / 10) for i in range(15)]
    m = moves.compute(pts, today=date(2026, 3, 1))
    assert "7d" not in m["changes"] and "30d" not in m["changes"] and "1y" in m["changes"]


def test_change_outlier_flagged_from_own_distribution():
    calm = [100 + (i % 3) * 0.5 for i in range(60)]
    m = moves.compute(series(calm + [140.0]), today=date(2025, 3, 3))
    assert m["unusual"] and "change" in m["unusual_reasons"] and m["change_z"] > moves.Z_LIMIT


def test_ordinary_wiggle_not_flagged():
    calm = [100 + (i % 3) * 0.5 for i in range(60)]
    m = moves.compute(series(calm + [100.5]), today=date(2025, 3, 3))
    assert m["unusual"] is False


def test_sustained_collapse_flagged_by_level_not_change():
    healthy = [100 + (i % 7) for i in range(300)]
    pts = series(healthy + [3.0, 3.0, 3.0, 3.0, 3.0])
    m = moves.compute(pts, today=pts[-1][0])
    assert "level" in m["unusual_reasons"] and m["level_z"] < -moves.Z_LIMIT and m["new_low"] == "90d"      # only ~300d of history: the 1y window is not covered


def test_long_regime_hides_from_trailing_year_but_not_from_full_record():
    healthy = [100 + (i % 7) for i in range(1500)]
    pts = series(healthy + [3 + (i % 4) for i in range(250)])           # a long collapse fills most of the last year
    m = moves.compute(pts, today=pts[-1][0])
    assert abs(m["level_z"]) < moves.Z_LIMIT and m["long_run_z"] < -moves.Z_LIMIT
    assert m["long_run_outside"] and not m["unusual"]       # a note beside the reading, not a flag


def test_flat_history_any_departure_is_unusual():
    pts = series([5.0] * 30 + [6.0])
    assert moves.compute(pts, today=pts[-1][0])["unusual"] is True
    assert moves.compute(series([5.0] * 31), today=date(2025, 2, 1))["unusual"] is False


def test_zero_valued_series_uses_differences_not_logs():
    pts = series([0.0, 3.0] * 20 + [0.0])
    assert moves.compute(pts, today=pts[-1][0])["changes"]["prev"]["abs"] == -3.0
    assert all(math.isfinite(x) for x in moves._steps(pts))


def test_as_of_replays_history():
    obs = [ob((date(2026, 1, 1) + timedelta(days=i)).isoformat(), float(i)) for i in range(30)]
    m = moves.series_moves(get_series("chk_hormuz_transits"), obs, as_of=date(2026, 1, 10))
    assert m["latest"]["period"] == "2026-01-10" and m["n_obs"] == 10
