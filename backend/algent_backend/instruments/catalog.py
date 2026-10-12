"""
The curated series catalog — code-defined, grouped by theme.

Adding a series is one entry here (plus one provider module in ``sources/`` if the provider is new).
Series ids are permanent: they name the store file and are cited by consumers. ``tags`` are what a
situation matches against — put the region, the actors and the dynamic ("hormuz", "iran", "gulf",
"shipping", "energy") so a desk working on any of them finds the number.

Every series declares its release ``cadence`` (how often the SOURCE publishes) and ``lag_days`` (typical days
from the end of a period to its publication); ``freshness.py`` judges "current" vs "overdue" against them, so a
weekly feed is never read as a broken daily one. Bases: PortWatch refreshes weekly (Tuesdays) with data to the
previous weekend, so ~7 days behind (observed: latest row 4 Oct on 11 Oct, a manual refetch returned nothing
newer); Yahoo, US Treasury and ECB publish each business day (next-day lag at most); Treasury FiscalData's debt
to the penny posts ~2 business days late; GIE AGSI+ posts the previous gas day each evening (revisions land the
next day); Eurostat's HICP flash estimate lands within ~2 days of month end (final figures ~17th).

Yahoo-backed series are ``public_display=False``: the endpoint is unofficial and its terms are
unreviewed, so they are internal evidence only. Government and central-bank sources are public.
"""

from __future__ import annotations

from .contracts import Series
from .live_series import LIVE_SERIES

_PORTWATCH_PAGE = "https://portwatch.imf.org/"
_PORTWATCH_LICENCE = "IMF PortWatch — open data, attribute IMF PortWatch; verify before public display"
_YAHOO_LICENCE = "Unofficial Yahoo endpoint; no published terms — internal only until reviewed"


_CHOKEPOINT_PLAIN = ("How many ships passed through {label} on a day. A chokepoint is a narrow passage that world "
                     "shipping has to squeeze through, so a sudden drop usually means closure, danger or rerouting.")
_CHOKEPOINT_TANKER_PLAIN = ("How many oil and fuel tankers passed through {label} on a day. A fall here "
                            "can tighten oil and gas supply and push prices up.")

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
    common = dict(unit="ships/day", frequency="daily", cadence="weekly", lag_days=7,
                  source="IMF PortWatch", source_url=_PORTWATCH_PAGE,
                  fetcher="portwatch", licence=_PORTWATCH_LICENCE, public_display=True,
                  tags=["chokepoint", "shipping", *tags])
    return [
        Series(id=f"chk_{slug}_transits", name=f"{label} — daily vessel transits",
               params={"port": port, "field": "n_total"}, plain=_CHOKEPOINT_PLAIN.format(label=label), **common),
        Series(id=f"chk_{slug}_tanker_transits", name=f"{label} — daily tanker transits",
               params={"port": port, "field": "n_tanker"}, plain=_CHOKEPOINT_TANKER_PLAIN.format(label=label),
               **{**common, "tags": [*common["tags"], "oil", "energy"]}),
    ]


def _yahoo(id: str, name: str, unit: str, symbol: str, tags: list[str], page: str, plain: str) -> Series:
    return Series(id=id, name=name, unit=unit, frequency="daily", source="Yahoo Finance", source_url=page,
                  fetcher="yahoo", params={"symbol": symbol}, tags=tags, licence=_YAHOO_LICENCE,
                  public_display=False, plain=plain)


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
           ["energy", "oil", "brent", "gulf", "hormuz", "iran", "russia", "opec"], _yf("BZ=F"),
           plain="The world benchmark price of a barrel of crude oil. It moves with Middle East and Russia supply fears and feeds into fuel prices everywhere."),
    _yahoo("px_wti", "WTI crude (front month)", "USD/bbl", "CL=F", ["energy", "oil", "wti", "us"], _yf("CL=F"),
           plain="The US benchmark price of a barrel of crude oil (West Texas Intermediate). Set against Brent it shows how much of an oil move is global and how much is American."),
    _yahoo("px_ttf_gas", "TTF European gas (front month)", "EUR/MWh", "TTF=F",
           ["energy", "gas", "europe", "russia", "lng", "ttf"], _yf("TTF=F"),
           plain="The benchmark price of natural gas in Europe (TTF, a Dutch trading hub), per megawatt-hour. It rises when Russian or Middle East gas is threatened and drives European power bills."),
    _yahoo("px_henry_gas", "Henry Hub natural gas (front month)", "USD/MMBtu", "NG=F",
           ["energy", "gas", "us", "lng"], _yf("NG=F"),
           plain="The benchmark price of natural gas in the US (Henry Hub, a Louisiana pipeline hub), per million BTU of heat. It runs far below European gas, which is why America exports liquefied gas."),
    Series(id="gas_eu_storage", name="EU gas storage fill", unit="% full", frequency="daily", lag_days=2,
           source="GIE AGSI+", source_url="https://agsi.gie.eu/", fetcher="agsi", params={"type": "eu"},
           tags=["energy", "gas", "europe", "russia", "storage"],
           licence="GIE AGSI+ — free, API key required (ALGENT_AGSI_KEY); GIE requires a visible 'GIE AGSI' source credit wherever it is shown",
           public_display=True,
           plain="How full Europe underground gas stores are. Full stores mean a safer winter; a low level makes the continent more exposed to supply cuts and price spikes."),
    Series(id="lng_eu_sendout", name="EU LNG terminal send-out", unit="GWh/day", frequency="daily", lag_days=2,
           source="GIE ALSI", source_url="https://alsi.gie.eu/", fetcher="alsi", params={"type": "eu", "field": "sendOut"},
           tags=["energy", "gas", "lng", "europe"],
           licence="GIE ALSI — free, same key as AGSI (ALGENT_AGSI_KEY); show a visible 'GIE ALSI' source credit", public_display=True,
           plain="How much liquefied natural gas (LNG, gas chilled into a liquid and shipped) Europe terminals are pushing into the pipe network each day. It shows how much Europe is leaning on shipped gas instead of pipelines."),
    Series(id="lng_eu_full", name="EU LNG terminal tanks, share full", unit="% full", frequency="daily", lag_days=2,
           source="GIE ALSI", source_url="https://alsi.gie.eu/", fetcher="alsi", params={"type": "eu", "field": "full"},
           tags=["energy", "gas", "lng", "europe", "storage"],
           licence="GIE ALSI — free, same key as AGSI (ALGENT_AGSI_KEY); show a visible 'GIE ALSI' source credit", public_display=True,
           plain="How full the storage tanks at Europe LNG terminals are. Tanks filling up mean ships are arriving; emptying tanks mean supply is tight."),

    # --- metals / food ---
    _yahoo("px_gold", "Gold (front month)", "USD/oz", "GC=F", ["metals", "gold", "safe-haven", "risk"], _yf("GC=F"),
           plain="The price of gold per ounce. People buy it when they fear war, inflation or a falling dollar, so a jump signals nervousness."),
    _yahoo("px_copper", "Copper (front month)", "USD/lb", "HG=F", ["metals", "copper", "china", "industry"], _yf("HG=F"),
           plain="The price of copper per pound. It tracks industrial demand, especially from China, so it works as a read on the global economy."),
    _yahoo("px_wheat", "Wheat (front month)", "USc/bu", "ZW=F",
           ["food", "grain", "wheat", "ukraine", "russia", "black-sea"], _yf("ZW=F"),
           plain="The price of wheat in US cents per bushel. Ukraine and Russia supply a large share of the world wheat, so war and blockades show up here."),

    # --- rates & FX ---
    Series(id="rate_ust_2y", name="US Treasury 2-year yield", unit="%", frequency="daily",
           source="US Treasury", source_url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
           fetcher="treasury", params={"column": "BC_2YEAR"}, tags=["rates", "us", "fed", "yields"],
           licence="US government work — public domain", public_display=True,
           plain="The interest rate the US government pays to borrow for two years. It mostly reflects what traders expect the US central bank to do with rates soon."),
    Series(id="rate_ust_10y", name="US Treasury 10-year yield", unit="%", frequency="daily",
           source="US Treasury", source_url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
           fetcher="treasury", params={"column": "BC_10YEAR"}, tags=["rates", "us", "fed", "yields"],
           licence="US government work — public domain", public_display=True,
           plain="The interest rate the US government pays to borrow for ten years. It sets the cost of mortgages and loans worldwide, and rises when investors want more reward for risk."),
    Series(id="rate_ecb_deposit", name="ECB deposit facility rate", unit="%", frequency="daily",
           source="European Central Bank", source_url="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/",
           fetcher="ecb", params={"flow": "FM", "key": "D.U2.EUR.4F.KR.DFR.LEV"}, tags=["rates", "europe", "ecb"],
           licence="ECB statistics — reuse with attribution; verify before public display", public_display=True,
           plain="The main interest rate set by the European Central Bank, which banks earn on cash parked there. Raising it cools inflation and slows the economy; cutting it does the opposite."),
    Series(id="fx_eurusd_ecb", name="EUR/USD (ECB reference rate)", unit="USD per EUR", frequency="daily",
           source="European Central Bank", source_url="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/",
           fetcher="ecb", params={"flow": "EXR", "key": "D.USD.EUR.SP00.A"}, tags=["fx", "europe", "us", "dollar"],
           licence="ECB statistics — reuse with attribution; verify before public display", public_display=True,
           plain="How many US dollars one euro buys, as fixed daily by the European Central Bank. A falling euro makes imports such as oil dearer for Europe."),
    _yahoo("fx_dxy", "US dollar index (DXY)", "index", "DX-Y.NYB", ["fx", "dollar", "us", "risk"], _yf("DX-Y.NYB"),
           plain="The US dollar index (DXY): the dollar against a basket of major currencies. A rising dollar tightens money for the rest of the world and often means investors are seeking safety."),
    _yahoo("fx_usdcny", "USD/CNY", "CNY per USD", "USDCNY=X", ["fx", "china", "yuan", "trade"], _yf("USDCNY=X"),
           plain="How many Chinese yuan one US dollar buys. A weaker yuan makes Chinese exports cheaper and often signals economic or trade stress."),
    _yahoo("fx_usdrub", "USD/RUB", "RUB per USD", "USDRUB=X", ["fx", "russia", "ruble", "sanctions"], _yf("USDRUB=X"),
           plain="How many Russian rubles one US dollar buys. It shows how sanctions and war spending are hitting the Russian economy."),

    # --- inflation & fiscal ---
    # prc_hicp_manr (COICOP) stopped updating in 2026-02 (stuck at 2025-12); Eurostat's ECOICOP-2 successor is prc_hicp_minr.
    Series(id="infl_ea_hicp", name="Euro-area inflation (HICP, annual rate)", unit="% y/y", frequency="monthly", cadence="monthly", lag_days=3,
           source="Eurostat", source_url="https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_minr/",
           fetcher="eurostat", params={"dataset": "prc_hicp_minr", "filters": {"geo": "EA", "coicop18": "TOTAL", "unit": "RCH_A"}},
           tags=["inflation", "europe", "ecb", "prices"],
           licence="Eurostat — reuse with attribution (Commission Decision 2011/833/EU)", public_display=True,
           plain="How much prices across the euro area rose over the past year (HICP is the EU standard inflation measure). The European Central Bank targets about 2 percent and sets interest rates by it."),
    Series(id="fisc_us_debt", name="US total public debt outstanding", unit="USD trillion", frequency="daily", lag_days=2,
           source="US Treasury FiscalData", source_url="https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/",
           fetcher="fiscaldata", params={"field": "tot_pub_debt_out_amt", "scale": 1e12},
           tags=["fiscal", "debt", "us"], licence="US government work — public domain", public_display=True,
           plain="The total the US federal government owes, in trillions of dollars. The bigger it grows, the more of the budget goes to interest and the less room there is for everything else."),

    # --- risk ---
    _yahoo("risk_vix", "VIX (equity volatility index)", "index", "^VIX", ["risk", "volatility", "equities", "us"], _yf("%5EVIX"),
           plain="The VIX, Wall Street fear gauge: how much swing investors expect in US stocks over the next month. Low is calm; spikes mean markets are rattled."),
    # --- our own counts from live feeds (AIS gates, ADS-B regions, FIRMS boxes): see instruments/live_series.py ---
    *LIVE_SERIES,
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
