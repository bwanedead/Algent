"""Actors, structural layer: multi-year history from OWID, BIS policy rates, WITS ranked trade, the trade store.
Offline, on small inline payloads shaped like the real ones."""

from __future__ import annotations

import pytest

from algent_backend.actors import catalog, store
from algent_backend.actors.contracts import TradeRanking, TradeShare
from algent_backend.actors.sources import bis, owid, wits

AT = "2026-10-04T00:00:00+00:00"


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_ACTORS_STORE", str(tmp_path / "astore"))


def test_owid_keeps_a_decade_when_asked_and_only_the_newest_by_default() -> None:
    rows = ["iso_code,year,oil_production"] + [f"RUS,{y},{y - 2000}" for y in range(1990, 2025)] + ["RUS,2025,"]
    inds = [catalog.get("oil_prod")]
    newest = owid.parse_rows(rows, inds, AT)
    assert [o.year for o in newest] == [2024]
    kept = sorted(o.year for o in owid.parse_rows(rows, inds, AT, keep_years=catalog.HISTORY_YEARS))
    assert kept == list(range(2014, 2025))                                  # 2024 and ten years before it


def test_bis_policy_rate_is_the_latest_month_of_each_year_and_skips_nan_and_the_euro_area() -> None:
    csv_text = "\n".join(["REF_AREA,TIME_PERIOD,OBS_VALUE",
                          "RU,2025-03,21", "RU,2025-12,16", "RU,2026-08,14", "US,2026-08,NaN", "XM,2026-08,2", "ZZ,2026-08,1"])
    got = {(o.iso2, o.year): o.value for o in bis.parse_csv(csv_text, catalog.get("policy_rate"), AT)}
    assert got == {("RU", 2025): 16.0, ("RU", 2026): 14.0}


def _sdmx(dim_values: list[str], values: list[float], dim: int) -> dict:
    """An SDMX-JSON payload with one series dimension (index ``dim``) holding ``dim_values``."""
    dims = [{"values": [{"id": "x"}]} for _ in range(5)]
    dims[dim] = {"values": [{"id": v} for v in dim_values]}
    series = {":".join(str(i if d == dim else 0) for d in range(5)): {"observations": {"0": [v, 0]}}
              for i, v in enumerate(values)}
    return {"structure": {"dimensions": {"series": dims}}, "dataSets": [{"series": series}]}


def test_wits_ranks_partners_and_products_with_legacy_codes_aggregates_and_units() -> None:
    partners = _sdmx(["WLD", "CHN", "DEU", "SUD", "EAS", "RUS", "ABW"], [1000.0, 300.0, 200.0, 50.0, 9000.0, 10.0, 0.0], 2)
    products = _sdmx(["27-27_Fuels", "84-85_MachElec", "Total", "Fuels", "72-83_Metals"], [500.0, 300.0, 1000.0, 500.0, 0.0], 3)
    r = wits.build(partners, products, iso2="RU", year=2021, flow="exports", source_url="u", fetched_at=AT)
    assert r is not None and r.total == 1_000_000.0                              # US$ thousand -> US$
    assert [p.id for p in r.partners] == ["CN", "DE", "SD"]                      # SUD is Sudan; EAS aggregate, RUS itself, 0 dropped
    assert [(p.name, p.value) for p in r.products] == [("Fuels (oil, gas, coal)", 500_000.0), ("Machinery and electronics", 300_000.0)]
    assert wits.build(_sdmx(["WLD"], [5.0], 2), products, iso2="RU", year=2021, flow="exports", source_url="u", fetched_at=AT) is None


def test_trade_store_appends_new_and_revised_only_and_serves_the_newest_year() -> None:
    def row(year: int, v: float) -> TradeRanking:
        return TradeRanking(iso2="RU", year=year, flow="exports", total=100.0, products=[TradeShare(id="p", name="P", value=v)],
                            partners=[TradeShare(id="CN", name="China", value=v)], source="wits", source_url="u", fetched_at=AT)

    assert store.append_trade([row(2020, 10.0), row(2021, 20.0)]).new == 2
    again = store.append_trade([row(2021, 20.0), row(2020, 11.0)])
    assert (again.new, again.revised, again.unchanged) == (0, 1, 1)
    assert len(store.trade_log()) == 3 and store.latest_trade()[("RU", "exports")].year == 2021


def test_store_series_is_one_countrys_annual_readings_oldest_first() -> None:
    from algent_backend.actors.contracts import Observation

    store.append("gdp", [Observation(iso2=c, indicator="gdp", year=y, value=float(y), source="wb", source_url="u", fetched_at=AT)
                         for c in ("RU", "US") for y in (2024, 2022, 2023)])
    assert store.series("gdp", "RU") == [(2022, 2022.0), (2023, 2023.0), (2024, 2024.0)]
