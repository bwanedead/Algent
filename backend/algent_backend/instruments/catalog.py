"""
The curated series catalog — code-defined, grouped by theme.

Adding a series is one entry here (plus one provider module in ``sources/`` if the provider is new).
Series ids are permanent: they name the store file and are cited by consumers. ``tags`` are what a
situation matches against — put the region, the actors and the dynamic ("hormuz", "iran", "gulf",
"shipping", "energy") so a desk working on any of them finds the number.

Yahoo-backed series are ``public_display=False``: the endpoint is unofficial and its terms are
unreviewed, so they are internal evidence only. Government and central-bank sources are public.
"""

from __future__ import annotations

from .contracts import Series

_PORTWATCH_PAGE = "https://portwatch.imf.org/"
_PORTWATCH_LICENCE = "IMF PortWatch — open data, attribute IMF PortWatch; verify before public display"
_YAHOO_LICENCE = "Unofficial Yahoo endpoint; no published terms — internal only until reviewed"


#: Where each tracked chokepoint sits, for maps. PortWatch's feature service carries no coordinates for
#: these ports (the query returns date/portname/counts only), so they are set by hand at the narrowest
#: point of the passage (approximate, ~10 km). Filled by ``_chokepoint``; read via ``chokepoint_sites()``.
_SITES: list[dict] = []


def chokepoint_sites() -> list[dict]:
    """[{series_id, label, lat, lon}] — one per tracked chokepoint; ``series_id`` is its all-vessel series."""
    return [dict(s) for s in _SITES]


def _chokepoint(slug: str, label: str, port: str, tags: list[str], lat: float, lon: float) -> list[Series]:
    """Two series per chokepoint: all-vessel transits and tanker transits (a Hormuz/oil lens)."""
    _SITES.append({"series_id": f"chk_{slug}_transits", "label": label, "lat": lat, "lon": lon})
    common = dict(unit="ships/day", frequency="daily", source="IMF PortWatch", source_url=_PORTWATCH_PAGE,
                  fetcher="portwatch", licence=_PORTWATCH_LICENCE, public_display=True,
                  tags=["chokepoint", "shipping", *tags])
    return [
        Series(id=f"chk_{slug}_transits", name=f"{label} — daily vessel transits",
               params={"port": port, "field": "n_total"}, **common),
        Series(id=f"chk_{slug}_tanker_transits", name=f"{label} — daily tanker transits",
               params={"port": port, "field": "n_tanker"}, **{**common, "tags": [*common["tags"], "oil", "energy"]}),
    ]


def _yahoo(id: str, name: str, unit: str, symbol: str, tags: list[str], page: str) -> Series:
    return Series(id=id, name=name, unit=unit, frequency="daily", source="Yahoo Finance", source_url=page,
                  fetcher="yahoo", params={"symbol": symbol}, tags=tags, licence=_YAHOO_LICENCE,
                  public_display=False)


def _yf(symbol: str) -> str:
    return f"https://finance.yahoo.com/quote/{symbol}/"


CATALOG: list[Series] = [
    # --- chokepoints: what actually moved through the straits (IMF PortWatch, ~1 week lag) ---
    *_chokepoint("hormuz", "Strait of Hormuz", "Strait of Hormuz", ["hormuz", "iran", "gulf", "oil", "energy"], 26.57, 56.25),
    *_chokepoint("bab_el_mandeb", "Bab el-Mandeb", "Bab el-Mandeb Strait", ["bab-el-mandeb", "red-sea", "yemen", "houthi"], 12.58, 43.33),
    *_chokepoint("suez", "Suez Canal", "Suez Canal", ["suez", "egypt", "red-sea"], 30.46, 32.35),
    *_chokepoint("panama", "Panama Canal", "Panama Canal", ["panama", "americas", "drought"], 9.08, -79.68),
    *_chokepoint("malacca", "Strait of Malacca", "Malacca Strait", ["malacca", "asia", "china", "singapore"], 2.5, 101.2),
    *_chokepoint("bosporus", "Bosporus", "Bosporus Strait", ["bosporus", "turkey", "black-sea", "russia", "ukraine"], 41.12, 29.07),
    *_chokepoint("cape", "Cape of Good Hope", "Cape of Good Hope", ["cape-of-good-hope", "africa", "red-sea", "rerouting"], -34.36, 18.47),

    # --- energy ---
    _yahoo("px_brent", "Brent crude (front month)", "USD/bbl", "BZ=F",
           ["energy", "oil", "brent", "gulf", "hormuz", "iran", "russia", "opec"], _yf("BZ=F")),
    _yahoo("px_wti", "WTI crude (front month)", "USD/bbl", "CL=F", ["energy", "oil", "wti", "us"], _yf("CL=F")),
    _yahoo("px_ttf_gas", "TTF European gas (front month)", "EUR/MWh", "TTF=F",
           ["energy", "gas", "europe", "russia", "lng", "ttf"], _yf("TTF=F")),
    _yahoo("px_henry_gas", "Henry Hub natural gas (front month)", "USD/MMBtu", "NG=F",
           ["energy", "gas", "us", "lng"], _yf("NG=F")),
    Series(id="gas_eu_storage", name="EU gas storage fill", unit="% full", frequency="daily",
           source="GIE AGSI+", source_url="https://agsi.gie.eu/", fetcher="agsi", params={"type": "eu"},
           tags=["energy", "gas", "europe", "russia", "storage"],
           licence="GIE AGSI+ — free, API key required (ALGENT_AGSI_KEY); attribute GIE; verify before public display",
           public_display=False),

    # --- metals / food ---
    _yahoo("px_gold", "Gold (front month)", "USD/oz", "GC=F", ["metals", "gold", "safe-haven", "risk"], _yf("GC=F")),
    _yahoo("px_copper", "Copper (front month)", "USD/lb", "HG=F", ["metals", "copper", "china", "industry"], _yf("HG=F")),
    _yahoo("px_wheat", "Wheat (front month)", "USc/bu", "ZW=F",
           ["food", "grain", "wheat", "ukraine", "russia", "black-sea"], _yf("ZW=F")),

    # --- rates & FX ---
    Series(id="rate_ust_2y", name="US Treasury 2-year yield", unit="%", frequency="daily",
           source="US Treasury", source_url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
           fetcher="treasury", params={"column": "BC_2YEAR"}, tags=["rates", "us", "fed", "yields"],
           licence="US government work — public domain", public_display=True),
    Series(id="rate_ust_10y", name="US Treasury 10-year yield", unit="%", frequency="daily",
           source="US Treasury", source_url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
           fetcher="treasury", params={"column": "BC_10YEAR"}, tags=["rates", "us", "fed", "yields"],
           licence="US government work — public domain", public_display=True),
    Series(id="rate_ecb_deposit", name="ECB deposit facility rate", unit="%", frequency="daily",
           source="European Central Bank", source_url="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/",
           fetcher="ecb", params={"flow": "FM", "key": "D.U2.EUR.4F.KR.DFR.LEV"}, tags=["rates", "europe", "ecb"],
           licence="ECB statistics — reuse with attribution; verify before public display", public_display=True),
    Series(id="fx_eurusd_ecb", name="EUR/USD (ECB reference rate)", unit="USD per EUR", frequency="daily",
           source="European Central Bank", source_url="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/",
           fetcher="ecb", params={"flow": "EXR", "key": "D.USD.EUR.SP00.A"}, tags=["fx", "europe", "us", "dollar"],
           licence="ECB statistics — reuse with attribution; verify before public display", public_display=True),
    _yahoo("fx_dxy", "US dollar index (DXY)", "index", "DX-Y.NYB", ["fx", "dollar", "us", "risk"], _yf("DX-Y.NYB")),
    _yahoo("fx_usdcny", "USD/CNY", "CNY per USD", "USDCNY=X", ["fx", "china", "yuan", "trade"], _yf("USDCNY=X")),
    _yahoo("fx_usdrub", "USD/RUB", "RUB per USD", "USDRUB=X", ["fx", "russia", "ruble", "sanctions"], _yf("USDRUB=X")),

    # --- inflation & fiscal ---
    Series(id="infl_ea_hicp", name="Euro-area inflation (HICP, annual rate)", unit="% y/y", frequency="monthly",
           source="Eurostat", source_url="https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_manr/",
           fetcher="eurostat", params={"dataset": "prc_hicp_manr", "filters": {"geo": "EA", "coicop": "CP00"}},
           tags=["inflation", "europe", "ecb", "prices"],
           licence="Eurostat — reuse with attribution (Commission Decision 2011/833/EU)", public_display=True),
    Series(id="fisc_us_debt", name="US total public debt outstanding", unit="USD trillion", frequency="daily",
           source="US Treasury FiscalData", source_url="https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/",
           fetcher="fiscaldata", params={"field": "tot_pub_debt_out_amt", "scale": 1e12},
           tags=["fiscal", "debt", "us"], licence="US government work — public domain", public_display=True),

    # --- risk ---
    _yahoo("risk_vix", "VIX (equity volatility index)", "index", "^VIX", ["risk", "volatility", "equities", "us"], _yf("%5EVIX")),
]

_BY_ID = {s.id: s for s in CATALOG}
assert len(_BY_ID) == len(CATALOG), "duplicate series id in the catalog"


def get_series(series_id: str) -> Series:
    try:
        return _BY_ID[series_id]
    except KeyError:
        raise KeyError(f"unknown instrument series {series_id!r}; known: {', '.join(sorted(_BY_ID))}") from None


def match(tags: list[str] | None) -> list[Series]:
    """Series sharing at least one tag (case-insensitive); no tags = the whole catalog."""
    if not tags:
        return list(CATALOG)
    wanted = {t.lower() for t in tags}
    return [s for s in CATALOG if wanted & set(s.tags)]
