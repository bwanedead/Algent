"""
World Bank WITS merchandise trade (UN Comtrade; free, keyless SDMX-JSON) — a country's exports and imports ranked.

For one reporter and year, ``partner/all/product/Total`` ranks the partner countries and ``partner/wld/product/all``
the product groups (the 16 HS sections), each in US$ thousand. A reporter that did not file a year answers 404
"NoRecordsFound": the newest year with data inside ``LOOKBACK`` years is used, so a late filer shows its latest
year (the ranking carries its year) and a country that never reports (Sudan, Eritrea) has none.

WITS names a few partners with legacy Comtrade codes (ROM, SER, SUD, ZAR, TMP); ``LEGACY`` maps those to the codes
the registry knows. Aggregates (WLD, regions) and territories the registry does not rank are not partners.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from algent_backend.polite_http import SourceError, get

from .. import registry
from ..catalog import HEADERS
from ..contracts import TradeRanking, TradeShare, now_iso

API = "https://wits.worldbank.org/API/V1/SDMX/V21/datasource/tradestats-trade"
PAGE = "https://wits.worldbank.org/CountryProfile/en/Country/{iso3}/Year/LTST/Summary"
LOOKBACK = 8                 # years to probe back from last year before calling a reporter silent
MAX_PARTNERS = 25            # the file keeps a ranking's head, not 200 lines of dust
SECTION = re.compile(r"^\d\d-\d\d_")                 # the HS sections; the other product codes overlap them
LEGACY = {"ROM": "ROU", "SER": "SRB", "SUD": "SDN", "ZAR": "COD", "TMP": "TLS"}
FLOWS = {"exports": "XPRT-TRD-VL", "imports": "MPRT-TRD-VL"}
#: Friendlier names for the HS section codes WITS abbreviates.
PRODUCT_NAMES = {"01-05_Animal": "Animal products", "06-15_Vegetable": "Vegetable products", "16-24_FoodProd": "Foodstuffs",
                 "25-26_Minerals": "Minerals", "27-27_Fuels": "Fuels (oil, gas, coal)", "28-38_Chemicals": "Chemicals",
                 "39-40_PlastiRub": "Plastics and rubber", "41-43_HidesSkin": "Hides and skins", "44-49_Wood": "Wood and paper",
                 "50-63_TextCloth": "Textiles and clothing", "64-67_Footwear": "Footwear", "68-71_StoneGlas": "Stone and glass",
                 "72-83_Metals": "Metals", "84-85_MachElec": "Machinery and electronics", "86-89_Transport": "Vehicles and transport",
                 "90-99_Miscellan": "Miscellaneous"}


def parse(payload: Any, dim: int) -> dict[str, float]:
    """{code of series dimension ``dim`` (2 = partner, 3 = product): US$ thousand} from an SDMX-JSON payload."""
    codes = [v["id"] for v in payload["structure"]["dimensions"]["series"][dim]["values"]]
    out: dict[str, float] = {}
    for key, series in payload["dataSets"][0]["series"].items():
        obs = series.get("observations", {}).get("0")
        if obs and obs[0] is not None:
            out[codes[int(key.split(":")[dim])]] = float(obs[0])
    return out


def _fetch(iso3: str, year: int, flow: str, partner: str, product: str) -> Any | None:
    url = f"{API}/reporter/{iso3.lower()}/year/{year}/partner/{partner}/product/{product}/indicator/{FLOWS[flow]}"
    body = get(url, {"format": "JSON"}, headers=HEADERS, missing_ok=True)
    return json.loads(body) if body else None


def build(partners_raw: Any, products_raw: Any, *, iso2: str, year: int, flow: str, source_url: str,
          fetched_at: str) -> TradeRanking | None:
    """A ranking from the two payloads; None when either is empty. The total is WITS's own world line."""
    by_partner = parse(partners_raw, 2)
    total = by_partner.get("WLD")
    partners = []
    for code, v in by_partner.items():
        other = registry.get(registry.iso2_of_iso3(LEGACY.get(code, code)) or "")
        if other is not None and other.iso2 != iso2 and other.kind == "state" and v > 0:
            partners.append(TradeShare(id=other.iso2, name=other.name, value=v * 1000))
    products = [TradeShare(id=c, name=PRODUCT_NAMES.get(c, c.split("_", 1)[-1]), value=v * 1000)
                for c, v in parse(products_raw, 3).items() if SECTION.match(c) and v > 0]
    if not total or not products or not partners:
        return None
    order = lambda s: (-s.value, s.id)                                                       # noqa: E731
    return TradeRanking(iso2=iso2, year=year, flow=flow, total=total * 1000, products=sorted(products, key=order),  # type: ignore[arg-type]
                        partners=sorted(partners, key=order)[:MAX_PARTNERS], source="wits", source_url=source_url,
                        fetched_at=fetched_at)


def ranking(iso2: str, year: int, flow: str, fetched_at: str) -> TradeRanking | None:
    """One country-year-flow ranking, or None when the reporter filed nothing for that year."""
    country = registry.get(iso2)
    if country is None:
        return None
    partners_raw = _fetch(country.iso3, year, flow, "all", "Total")
    products_raw = _fetch(country.iso3, year, flow, "wld", "all") if partners_raw else None
    if not partners_raw or not products_raw:
        return None
    return build(partners_raw, products_raw, iso2=iso2, year=year, flow=flow, fetched_at=fetched_at,
                 source_url=PAGE.format(iso3=country.iso3))


def fetch(iso2s: list[str], today: date | None = None) -> tuple[list[TradeRanking], dict[str, str]]:
    """Rankings for each country (both flows, its newest year with data) and {iso2: reason} for the silent ones."""
    this_year = (today or date.today()).year
    fetched_at, out, silent = now_iso(), [], {}
    for iso2 in iso2s:
        try:
            got: list[TradeRanking] = []
            for year in range(this_year - 1, this_year - 1 - LOOKBACK, -1):
                first = ranking(iso2, year, "exports", fetched_at)
                if first is None:
                    continue
                second = ranking(iso2, year, "imports", fetched_at)
                got = [first, *([second] if second else [])]
                break
            out += got
            if not got:
                silent[iso2] = f"no WITS filing in {this_year - LOOKBACK}-{this_year - 1}"
        except (SourceError, ValueError, KeyError, IndexError) as exc:
            silent[iso2] = f"{type(exc).__name__}: {str(exc)[:100]}"
    return out, silent
