"""Provider parsers against one captured real response each (fixtures/instruments/)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from algent_backend.instruments.catalog import get_series
from algent_backend.instruments.http import SourceUnavailable
from algent_backend.instruments.sources import agsi, ecb, eurostat, fiscaldata, portwatch, treasury, yahoo

FIX = Path(__file__).parent / "fixtures" / "instruments"
T = "2026-10-04T00:00:00+00:00"


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_portwatch_total_and_tanker_from_one_payload():
    total = portwatch.parse(read("portwatch.json"), get_series("chk_hormuz_transits"), T)
    tank = portwatch.parse(read("portwatch.json"), get_series("chk_hormuz_tanker_transits"), T)
    assert len(total) == 8 and total[0].period == "2026-09-27" and total[0].value == 1.0
    assert [o.period for o in total] == [o.period for o in tank]
    assert total[0].source_url == get_series("chk_hormuz_transits").source_url


def test_portwatch_epoch_ms_dates():
    text = '{"features":[{"attributes":{"date":1790467200000,"n_total":5}}]}'
    obs = portwatch.parse(text, get_series("chk_hormuz_transits"), T)
    assert obs[0].period == "2026-09-27"


def test_yahoo_closes_use_exchange_local_date():
    obs = yahoo.parse(read("yahoo.json"), get_series("px_brent"), T)
    assert len(obs) == 4 and obs[-1].value == 102.25
    assert all(o.period.startswith("2026-09") or o.period.startswith("2026-10") for o in obs)


def test_yahoo_range_picks_smallest_cover():
    today = date(2026, 10, 4)
    assert yahoo.range_for(None, today) == "1mo"
    assert yahoo.range_for(date(2026, 9, 1), today) == "3mo"
    assert yahoo.range_for(date(2021, 10, 5), today) == "5y"
    assert yahoo.range_for(date(2010, 1, 1), today) == "10y"


def test_treasury_picks_requested_tenor():
    two = treasury.parse(read("treasury_yields.xml"), get_series("rate_ust_2y"), T)
    ten = treasury.parse(read("treasury_yields.xml"), get_series("rate_ust_10y"), T)
    assert len(two) == len(ten) == 3 and two[0].period == "2026-09-01" and two[0].value == 4.39
    assert ten[0].value != two[0].value


def test_treasury_month_window():
    assert treasury._months(None, date(2026, 1, 15)) == ["202512", "202601"]
    assert treasury._months(date(2026, 11, 20), date(2027, 1, 2)) == ["202611", "202612", "202701"]


def test_fiscaldata_scales_to_trillions():
    obs = fiscaldata.parse(read("debt.json"), get_series("fisc_us_debt"), T)
    assert obs[0].period == "2026-10-01" and obs[0].value == pytest.approx(40.2606, abs=1e-3)


def test_ecb_csv_for_fx_and_rate():
    fx = ecb.parse(read("ecb_fx.csv"), get_series("fx_eurusd_ecb"), T)
    assert fx[-1].period == "2026-10-02" and fx[-1].value == 1.1225
    rate = ecb.parse("TIME_PERIOD,OBS_VALUE\n2026-10-02,2.5\n", get_series("rate_ecb_deposit"), T)
    assert rate[0].value == 2.5


def test_eurostat_jsonstat_time_axis():
    obs = eurostat.parse(read("eurostat.json"), get_series("infl_ea_hicp"), T)
    assert (obs[0].period, obs[0].value) == ("2025-09", 2.2) and obs[-1].period == "2025-12"


def test_agsi_keyless_denial_degrades_to_unavailable(monkeypatch):
    s = get_series("gas_eu_storage")
    with pytest.raises(SourceUnavailable):
        agsi.parse(read("agsi_denied.json"), s, T)
    monkeypatch.delenv(agsi.KEY_ENV, raising=False)
    with pytest.raises(SourceUnavailable, match="API key"):
        agsi.fetch(s, None)       # no key: refuses before any network call


def test_agsi_parses_documented_shape():
    text = '{"data":[{"gasDayStart":"2026-10-01","full":"81.5"},{"gasDayStart":"2026-09-30","full":"-"}]}'
    obs = agsi.parse(text, get_series("gas_eu_storage"), T)
    assert [(o.period, o.value) for o in obs] == [("2026-10-01", 81.5)]
