"""Numbers and power: a theater's actors (annual structure, trends, ranked trade) and its physical-flow trackers.
Offline, deterministic."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from algent_backend.actors import store as astore
from algent_backend.actors.contracts import Leaders, Observation as AObs, Official, TradeRanking, TradeShare
from algent_backend.agent_system.agents.intel import numbers, render
from algent_backend.instruments import catalog
from algent_backend.instruments import store as istore
from algent_backend.instruments.contracts import Observation
from algent_backend.instruments.moves import series_moves

DAY = date(2026, 10, 4)
AT = "2026-10-04T00:00:00+00:00"


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_INSTRUMENTS_STORE", str(tmp_path / "istore"))
    monkeypatch.setenv("ALGENT_ACTORS_STORE", str(tmp_path / "astore"))


def _seed(sid: str, values: list[float], *, end: date = DAY) -> None:
    n = len(values)
    istore.append(sid, [Observation(series_id=sid, period=(end - timedelta(days=n - 1 - i)).isoformat(), value=v,
                                    fetched_at="t", source_url="u") for i, v in enumerate(values)])


def _row(sid: str, end: date = DAY) -> dict:
    return series_moves(catalog.get_series(sid), istore.history(sid), as_of=end, today=end)


# ── flow trackers ───────────────────────────────────────────────────────────────────────────────
def test_spark_is_bounded_ends_on_latest_and_covers_a_year() -> None:
    _seed("chk_hormuz_transits", [float(i) for i in range(1000)])        # ~2.7 years of daily data
    s = numbers.spark("chk_hormuz_transits", DAY)
    assert len(s) == numbers.SPARK_POINTS and s[-1] == 999.0
    assert s[0] >= 999 - numbers.SPARK_DAYS and s == sorted(s)


def test_spark_of_a_sparse_series_draws_its_last_points_and_missing_is_empty() -> None:
    sid = "infl_ea_hicp"                                                   # monthly: a year is only 12 points
    istore.append(sid, [Observation(series_id=sid, period=f"{y}-{m:02d}", value=float(m), fetched_at="t", source_url="u")
                        for y, ms in ((2025, range(1, 13)), (2026, range(1, 10))) for m in ms])
    assert numbers.spark(sid, DAY)[-1] == 9.0 and len(numbers.spark(sid, DAY)) >= numbers.SPARK_MIN_POINTS
    assert numbers.spark("px_gold", DAY) == []


def test_tracker_changes_are_from_to_and_internal_sources_carry_no_url() -> None:
    _seed("chk_hormuz_transits", [100.0] * 30 + [90.0] * 20 + [99.0] * 6 + [110.0])
    t = numbers.tracker(_row("chk_hormuz_transits"), DAY)
    assert (t["id"], t["value"], t["as_of"], t["unit"]) == ("chk_hormuz_transits", 110.0, "2026-10-04", "ships/day")
    assert t["internal"] is False and t["source_url"].startswith("https://") and t["source"] == "IMF PortWatch"
    assert t["changes"]["prev"] == {"from": 99.0, "from_period": "2026-10-03", "pct": 11.11}
    assert set(t["changes"]) <= {"prev", "7d", "30d", "1y"} and t["spark"][-1] == 110.0
    assert t["unusual"] is True and "change" in t["reasons"]
    _seed("px_brent", [100.0] * 59 + [200.0])                                # Yahoo: unreviewed terms
    b = numbers.tracker(_row("px_brent"), DAY)
    assert b["internal"] is True and b["source_url"] == "" and b["source"] == "Yahoo Finance"


def test_only_physical_flows_and_policy_rates_become_trackers() -> None:
    for sid in ("chk_hormuz_transits", "rate_ecb_deposit", "px_brent", "fx_dxy", "px_gold", "rate_ust_10y"):
        _seed(sid, [50.0 + i % 3 for i in range(59)] + [60.0])
    rows = [_row(s) for s in ("px_brent", "fx_dxy", "chk_hormuz_transits", "px_gold", "rate_ecb_deposit", "rate_ust_10y")]
    out = numbers.trackers(rows, DAY)
    assert sorted(t["id"] for t in out) == ["chk_hormuz_transits", "rate_ecb_deposit"]        # no prices, no FX, no yields
    assert len(numbers.trackers([_row("chk_hormuz_transits")] * 20, DAY)) == numbers.MAX_TRACKERS
    assert out[0]["unusual"] or not out[1]["unusual"]                                           # unusual first


# ── actors ──────────────────────────────────────────────────────────────────────────────────────
def _seed_actors() -> None:
    def ob(ind, iso, v, y=2025, src="wb"):
        return AObs(iso2=iso, indicator=ind, year=y, value=v, source=src, source_url="u", fetched_at=AT)

    for iso, pop, gdp in (("RU", 143e6, 2.5e12), ("UA", 38e6, 2.1e11), ("US", 340e6, 3e13), ("IR", 92e6, 3.6e11),
                          ("YE", 41e6, 2e10), ("SD", 51e6, 6e10)):
        astore.append("population", [ob("population", iso, pop)])
        astore.append("gdp", [ob("gdp", iso, gdp * (1 + 0.1 * (y - 2025)), y) for y in range(2015, 2026)] if iso == "RU"
                      else [ob("gdp", iso, gdp)])
    astore.append("energy_import_pct", [ob("energy_import_pct", "RU", -75.0), ob("energy_import_pct", "UA", 23.0)])
    astore.append("fiscal_balance_imf", [ob("fiscal_balance_imf", "RU", -2.0, 2025, "imf")])
    astore.append_leaders([Leaders(iso2="RU", head_of_state=Official(name="Vladimir Putin"), fetched_at=AT,
                                   source_url="s")])
    share = lambda i, n, v: TradeShare(id=i, name=n, value=v)                                    # noqa: E731
    astore.append_trade([TradeRanking(
        iso2="RU", year=2021, flow="exports", total=1000.0,
        products=[share(f"p{i}", f"Product {i}", 300.0 - 40 * i) for i in range(7)],
        partners=[share("CN", "China", 140.0), share("DE", "Germany", 60.0)] + [share("FR", "France", 10.0)] * 5,
        source="wits", source_url="u", fetched_at=AT)])


def test_actor_codes_resolve_names_semantically_rank_by_mentions_and_ignore_the_sea() -> None:
    section = {"developments": [
        {"actors": ["Russia", "Ukraine (military spokesman X)"], "place": {"country": "Ukraine"}},
        {"actors": ["Russia", "Russia"], "place": {"country": "sea"}},           # once per development
        {"actors": ["Rapid Support Forces (RSF)", "Houthis"], "place": None},    # not countries: never scanned
    ], "on_record": [{"iso2": "US", "about_iso2": ["RU"]}, {"iso2": "", "about_iso2": []}]}
    brief = {"relations": [{"source": "Ukraine", "target": "Russia"}, {"source": "A->B", "target": "Atlantis"}]}
    codes = numbers.actor_codes(section, brief)
    assert codes[:2] == ["RU", "UA"] and "US" in codes and len(codes) == 3     # RU 4, UA 3, US 1
    assert numbers.actor_codes({}, None) == []


def test_actor_block_carries_year_rank_trend_and_ranked_trade() -> None:
    _seed_actors()
    block = numbers.actor_block(["RU", "FR", "UA", "US", "IR", "YE", "SD"])    # FR: nothing stored
    assert [a["iso2"] for a in block] == ["RU", "UA", "US", "IR", "YE"] and len(block) == numbers.MAX_ACTORS
    ru = block[0]
    assert ru["leaders"] == {"head_of_state": "Vladimir Putin"} and ru["name"] == "Russia"
    assert ru["metrics"]["population"] == {"label": "Population", "unit": "people", "value": 143e6, "year": 2025,
                                           "rank": 2, "of": 6, "source": "wb"}          # no trend: one year stored
    gdp = ru["metrics"]["gdp"]
    assert gdp["trend"][0][0] == 2015 and gdp["trend"][-1] == [2025, 2.5e12] and len(gdp["trend"]) == 11
    assert ru["metrics"]["energy_import_pct"]["value"] == -75.0 and "milex" not in ru["metrics"]
    assert ru["metrics"]["fiscal_balance_imf"]["source"] == "imf"
    ex = ru["trade"]["exports"]
    assert ex["year"] == 2021 and len(ex["products"]) == numbers.TOP_RANKED == len(ex["partners"])
    assert ex["products"][0] == {"name": "Product 0", "value": 300.0, "share": 30.0}
    assert ex["partners"][0] == {"iso2": "CN", "name": "China", "value": 140.0, "share": 14.0}
    assert "imports" not in ru["trade"] and block[1]["trade"] == {}


def test_for_section_builds_both_halves_and_survives_bad_input() -> None:
    _seed_actors()
    _seed("chk_hormuz_transits", [100.0] * 59 + [200.0])
    sec = {"developments": [{"actors": ["Russia", "Ukraine"], "place": None}], "on_record": []}
    n = numbers.for_section(sec, [_row("chk_hormuz_transits")], None, as_of="2026-10-04")
    assert [t["id"] for t in n["trackers"]] == ["chk_hormuz_transits"] and [a["iso2"] for a in n["actors"]] == ["RU", "UA"]
    assert n["as_of"] == "2026-10-04" and "trackers_error" not in n
    bad = numbers.for_section({"developments": [{"actors": 5}]}, [{"nope": 1}], None, as_of="2026-10-04")
    assert bad["trackers"] == [] and "trackers_error" in bad                  # a part that fails is just empty


def test_html_renderer_accepts_records_without_markets() -> None:
    base = {"schema": "ohmega.daily/1", "domain": "geopolitics", "date": "2026-10-04", "summary": {"headline": "h",
            "the_day": []}, "theaters": [], "cross_theater": [], "watch": [], "quiet": [], "pulse_proposals": []}
    assert render.render_daily(base)
