"""
The indicator catalog and the source credits — code-defined, grouped by theme.

Adding an indicator is one entry in ``INDICATORS`` (a World Bank code, an OWID column or an IMF series
that an existing source already fetches). Ids are permanent: they name the store file and are cited by
consumers. ``SOURCES`` carries the credit line each page must print (all keyless, open licences).
"""

from __future__ import annotations

from pydantic import BaseModel

from .contracts import Group, Indicator, Unit


#: Open-data hosts ask bulk clients to identify themselves (the IMF refuses browser-looking agents outright).
USER_AGENT = "OhmegaActors/1.0 (https://ohmega.monster; bettsryan5@gmail.com) httpx"
HEADERS = {"User-Agent": USER_AGENT}


#: Annual statistics are kept for this many years back, so a page can draw a ten-year trend.
HISTORY_YEARS = 10


class Source(BaseModel):
    key: str
    name: str
    licence: str
    url: str                 # the human page to credit


SOURCES: dict[str, Source] = {s.key: s for s in (
    Source(key="wb", name="World Bank World Development Indicators (military figures: SIPRI)",
           licence="CC BY 4.0", url="https://data.worldbank.org/"),
    Source(key="owid", name="Our World in Data energy dataset (Energy Institute, Ember, EIA)",
           licence="CC BY 4.0", url="https://ourworldindata.org/energy"),
    Source(key="imf", name="IMF World Economic Outlook (DataMapper)",
           licence="IMF open data, attribution", url="https://www.imf.org/external/datamapper"),
    Source(key="bis", name="Bank for International Settlements, central bank policy rates",
           licence="BIS statistics, free reuse with attribution", url="https://data.bis.org/topics/CBPOL"),
    Source(key="wits", name="World Bank WITS (UN Comtrade merchandise trade)",
           licence="WITS terms of use: free with attribution", url="https://wits.worldbank.org/"),
    Source(key="wikidata", name="Wikidata (heads of state and government)", licence="CC0",
           url="https://www.wikidata.org/"),
    Source(key="nuclear", name="Federation of American Scientists, Status of World Nuclear Forces",
           licence="public statements, cited", url="https://fas.org/initiatives/status-world-nuclear-forces/"),
)}


def _i(id: str, source: str, code: str, label: str, unit: Unit, group: Group) -> Indicator:
    return Indicator(id=id, source=source, code=code, label=label, unit=unit, group=group)


INDICATORS: list[Indicator] = [
    # --- people ---
    _i("population", "wb", "SP.POP.TOTL", "Population", "people", "people"),
    _i("pop_growth", "wb", "SP.POP.GROW", "Population growth", "pct", "people"),
    _i("urban_pct", "wb", "SP.URB.TOTL.IN.ZS", "Urban population", "pct", "people"),
    _i("land_area", "wb", "AG.LND.TOTL.K2", "Land area", "km2", "people"),
    # --- economy ---
    _i("gdp", "wb", "NY.GDP.MKTP.CD", "GDP", "usd", "economy"),
    _i("gdp_ppp", "wb", "NY.GDP.MKTP.PP.CD", "GDP (purchasing power)", "usd", "economy"),
    _i("gdp_pc", "wb", "NY.GDP.PCAP.CD", "GDP per person", "usd", "economy"),
    _i("gdp_pc_ppp", "wb", "NY.GDP.PCAP.PP.CD", "GDP per person (purchasing power)", "usd", "economy"),
    _i("gdp_growth", "wb", "NY.GDP.MKTP.KD.ZG", "GDP growth", "pct", "economy"),
    _i("inflation", "wb", "FP.CPI.TOTL.ZG", "Inflation", "pct", "economy"),
    _i("gov_debt", "wb", "GC.DOD.TOTL.GD.ZS", "Central government debt, share of GDP", "pct", "economy"),
    _i("gdp_growth_imf", "imf", "NGDP_RPCH", "GDP growth, IMF estimate/forecast", "pct", "economy"),
    _i("gov_debt_imf", "imf", "GGXWDG_NGDP", "General government gross debt, share of GDP (IMF)", "pct", "economy"),
    _i("fiscal_balance_imf", "imf", "GGXCNL_NGDP", "Government net lending/borrowing, share of GDP (IMF)", "pct", "economy"),
    _i("current_account_imf", "imf", "BCA_NGDPD", "Current account balance, share of GDP (IMF)", "pct", "economy"),
    _i("reserves_usd", "wb", "FI.RES.TOTL.CD", "Foreign reserves (incl. gold)", "usd", "economy"),
    _i("reserves_months", "wb", "FI.RES.TOTL.MO", "Foreign reserves, months of imports", "months", "economy"),
    _i("ext_debt_usd", "wb", "DT.DOD.DECT.CD", "External debt stocks", "usd", "economy"),
    _i("ext_debt_gni", "wb", "DT.DOD.DECT.GN.ZS", "External debt, share of national income", "pct", "economy"),
    _i("policy_rate", "bis", "WS_CBPOL", "Central bank policy rate (end of year)", "pct", "economy"),
    # --- trade ---
    _i("exports_pct", "wb", "NE.EXP.GNFS.ZS", "Exports, share of GDP", "pct", "trade"),
    _i("imports_pct", "wb", "NE.IMP.GNFS.ZS", "Imports, share of GDP", "pct", "trade"),
    _i("fuel_exports_pct", "wb", "TX.VAL.FUEL.ZS.UN", "Fuels, share of goods exports", "pct", "trade"),
    _i("exports_usd", "wb", "NE.EXP.GNFS.CD", "Exports of goods and services", "usd", "trade"),
    _i("imports_usd", "wb", "NE.IMP.GNFS.CD", "Imports of goods and services", "usd", "trade"),
    _i("food_exports_pct", "wb", "TX.VAL.FOOD.ZS.UN", "Food, share of goods exports", "pct", "trade"),
    _i("metal_exports_pct", "wb", "TX.VAL.MMTL.ZS.UN", "Ores and metals, share of goods exports", "pct", "trade"),
    _i("manuf_exports_pct", "wb", "TX.VAL.MANF.ZS.UN", "Manufactures, share of goods exports", "pct", "trade"),
    _i("fuel_imports_pct", "wb", "TM.VAL.FUEL.ZS.UN", "Fuels, share of goods imports", "pct", "trade"),
    _i("food_imports_pct", "wb", "TM.VAL.FOOD.ZS.UN", "Food, share of goods imports", "pct", "trade"),
    _i("metal_imports_pct", "wb", "TM.VAL.MMTL.ZS.UN", "Ores and metals, share of goods imports", "pct", "trade"),
    _i("manuf_imports_pct", "wb", "TM.VAL.MANF.ZS.UN", "Manufactures, share of goods imports", "pct", "trade"),
    # --- energy (OWID, TWh unless noted) ---
    _i("energy_use", "owid", "primary_energy_consumption", "Primary energy consumption", "twh", "energy"),
    _i("energy_pc", "owid", "energy_per_capita", "Energy use per person", "kwh", "energy"),
    _i("oil_prod", "owid", "oil_production", "Oil production", "twh", "energy"),
    _i("gas_prod", "owid", "gas_production", "Gas production", "twh", "energy"),
    _i("coal_prod", "owid", "coal_production", "Coal production", "twh", "energy"),
    _i("oil_cons", "owid", "oil_consumption", "Oil consumption", "twh", "energy"),
    _i("gas_cons", "owid", "gas_consumption", "Gas consumption", "twh", "energy"),
    _i("coal_cons", "owid", "coal_consumption", "Coal consumption", "twh", "energy"),
    _i("elec_gen", "owid", "electricity_generation", "Electricity generation", "twh", "energy"),
    _i("elec_fossil", "owid", "fossil_share_elec", "Electricity from fossil fuels", "pct", "energy"),
    _i("elec_nuclear", "owid", "nuclear_share_elec", "Electricity from nuclear", "pct", "energy"),
    _i("elec_renew", "owid", "renewables_share_elec", "Electricity from renewables", "pct", "energy"),
    _i("energy_import_pct", "wb", "EG.IMP.CONS.ZS", "Net energy imports, share of use", "pct", "energy"),
    # --- military ---
    _i("milex", "wb", "MS.MIL.XPND.CD", "Military spending", "usd", "military"),
    _i("milex_pct", "wb", "MS.MIL.XPND.GD.ZS", "Military spending, share of GDP", "pct", "military"),
    _i("armed_forces", "wb", "MS.MIL.TOTL.P1", "Armed forces personnel", "persons", "military"),
    _i("arms_imports", "wb", "MS.MIL.MPRT.KD", "Arms imports (SIPRI trend-indicator value, 1990 US$)", "usd", "military"),
    _i("arms_exports", "wb", "MS.MIL.XPRT.KD", "Arms exports (SIPRI trend-indicator value, 1990 US$)", "usd", "military"),
]

_BY_ID = {i.id: i for i in INDICATORS}


def get(indicator_id: str) -> Indicator:
    try:
        return _BY_ID[indicator_id]
    except KeyError:
        raise KeyError(f"unknown indicator {indicator_id!r}") from None


def for_source(source: str) -> list[Indicator]:
    return [i for i in INDICATORS if i.source == source]
