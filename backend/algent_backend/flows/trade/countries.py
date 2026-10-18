"""
Countries on the trade layer — the UN Comtrade numeric code(s) of each, its ISO-2 code, and a point for its arc ends (pure data).

The point is the middle of the country's trade (roughly where its people and ports are), not its geographic centre: it is where a
drawn flow starts and ends, not a claim about a port. Comtrade uses its own codes for a few areas (France 251 incl. Monaco, Italy 381,
India 699, Norway 579, Switzerland 757, the USA 842, Belgium 56 and the old Belgium-Luxembourg 58); both codes map to one country.
"Other Asia, nes" (490) is how Taiwan is reported and is shown as Taiwan. Partners not listed here are dropped from the picture.
"""

from __future__ import annotations

from typing import NamedTuple


class Country(NamedTuple):
    iso2: str
    name: str
    lat: float
    lon: float
    codes: tuple[int, ...]


COUNTRIES: tuple[Country, ...] = (
    Country("US", "United States", 39.0, -96.0, (842, 841, 840)), Country("CA", "Canada", 52.0, -100.0, (124,)),
    Country("MX", "Mexico", 23.6, -102.5, (484,)), Country("BR", "Brazil", -14.0, -52.0, (76,)), Country("AR", "Argentina", -34.0, -62.0, (32,)),
    Country("CL", "Chile", -30.0, -71.0, (152,)), Country("CO", "Colombia", 4.5, -73.0, (170,)), Country("PE", "Peru", -9.2, -75.0, (604,)),
    Country("EC", "Ecuador", -1.4, -78.4, (218,)), Country("VE", "Venezuela", 7.0, -66.0, (862,)), Country("PY", "Paraguay", -23.0, -58.0, (600,)),
    Country("UY", "Uruguay", -33.0, -56.0, (858,)), Country("CU", "Cuba", 21.5, -79.5, (192,)), Country("DO", "Dominican Republic", 19.0, -70.7, (214,)),
    Country("GT", "Guatemala", 15.5, -90.3, (320,)),
    Country("GB", "United Kingdom", 53.0, -1.5, (826,)), Country("IE", "Ireland", 53.2, -8.0, (372,)), Country("FR", "France", 46.6, 2.3, (251, 250)),
    Country("DE", "Germany", 51.0, 10.0, (276,)), Country("NL", "Netherlands", 52.2, 5.3, (528,)), Country("BE", "Belgium", 50.6, 4.7, (56, 58)),
    Country("ES", "Spain", 40.0, -4.0, (724,)), Country("PT", "Portugal", 39.5, -8.0, (620,)), Country("IT", "Italy", 42.8, 12.5, (381, 380)),
    Country("CH", "Switzerland", 46.8, 8.2, (757, 756)), Country("AT", "Austria", 47.6, 14.1, (40,)), Country("SE", "Sweden", 60.5, 15.0, (752,)),
    Country("NO", "Norway", 61.0, 9.0, (579, 578)), Country("DK", "Denmark", 56.0, 10.0, (208,)), Country("FI", "Finland", 62.0, 26.0, (246,)),
    Country("PL", "Poland", 52.0, 19.0, (616,)), Country("CZ", "Czechia", 49.8, 15.5, (203,)), Country("HU", "Hungary", 47.0, 19.5, (348,)),
    Country("RO", "Romania", 45.9, 25.0, (642,)), Country("BG", "Bulgaria", 42.7, 25.5, (100,)), Country("GR", "Greece", 39.0, 22.0, (300,)),
    Country("RS", "Serbia", 44.0, 21.0, (688,)), Country("HR", "Croatia", 45.1, 15.2, (191,)), Country("UA", "Ukraine", 49.0, 32.0, (804,)),
    Country("BY", "Belarus", 53.7, 27.9, (112,)), Country("RU", "Russia", 56.0, 40.0, (643,)), Country("TR", "Turkey", 39.0, 35.0, (792,)),
    Country("GE", "Georgia", 42.3, 43.4, (268,)), Country("AZ", "Azerbaijan", 40.3, 47.7, (31,)), Country("KZ", "Kazakhstan", 48.0, 67.0, (398,)),
    Country("UZ", "Uzbekistan", 41.4, 64.6, (860,)),
    Country("CN", "China", 33.0, 112.0, (156,)), Country("HK", "Hong Kong", 22.3, 114.2, (344,)), Country("TW", "Taiwan", 23.7, 121.0, (158, 490)),
    Country("JP", "Japan", 36.0, 138.0, (392,)), Country("KR", "South Korea", 36.5, 127.8, (410,)), Country("VN", "Vietnam", 16.0, 106.0, (704,)),
    Country("TH", "Thailand", 15.0, 101.0, (764,)), Country("ID", "Indonesia", -2.0, 114.0, (360,)), Country("MY", "Malaysia", 4.0, 102.0, (458,)),
    Country("PH", "Philippines", 12.8, 122.0, (608,)), Country("SG", "Singapore", 1.35, 103.8, (702,)), Country("MM", "Myanmar", 21.0, 96.0, (104,)),
    Country("KH", "Cambodia", 12.7, 104.9, (116,)), Country("IN", "India", 21.0, 78.0, (699, 356)), Country("PK", "Pakistan", 30.0, 70.0, (586,)),
    Country("BD", "Bangladesh", 23.7, 90.3, (50,)), Country("LK", "Sri Lanka", 7.8, 80.7, (144,)),
    Country("SA", "Saudi Arabia", 24.0, 45.0, (682,)), Country("AE", "United Arab Emirates", 24.5, 54.5, (784,)), Country("QA", "Qatar", 25.3, 51.2, (634,)),
    Country("KW", "Kuwait", 29.3, 47.6, (414,)), Country("OM", "Oman", 21.0, 57.0, (512,)), Country("IR", "Iran", 32.0, 53.0, (364,)),
    Country("IQ", "Iraq", 33.0, 44.0, (368,)), Country("IL", "Israel", 31.5, 35.0, (376,)), Country("JO", "Jordan", 31.0, 36.5, (400,)),
    Country("YE", "Yemen", 15.5, 47.5, (887,)),
    Country("EG", "Egypt", 27.0, 30.0, (818,)), Country("MA", "Morocco", 32.0, -6.0, (504,)), Country("DZ", "Algeria", 28.0, 3.0, (12,)),
    Country("TN", "Tunisia", 34.0, 9.0, (788,)), Country("LY", "Libya", 27.0, 17.0, (434,)), Country("SD", "Sudan", 15.5, 30.0, (736,)),
    Country("NG", "Nigeria", 9.0, 8.0, (566,)), Country("GH", "Ghana", 7.9, -1.0, (288,)), Country("CI", "Cote d'Ivoire", 7.5, -5.5, (384,)),
    Country("KE", "Kenya", 0.5, 38.0, (404,)), Country("ET", "Ethiopia", 9.0, 40.0, (231, 230)), Country("TZ", "Tanzania", -6.4, 34.9, (834,)),
    Country("ZA", "South Africa", -29.0, 24.0, (710,)), Country("AO", "Angola", -12.0, 18.0, (24,)), Country("MZ", "Mozambique", -18.0, 35.0, (508,)),
    Country("AU", "Australia", -25.0, 134.0, (36,)), Country("NZ", "New Zealand", -41.0, 174.0, (554,)),
)

BY_CODE: dict[int, Country] = {code: c for c in COUNTRIES for code in c.codes}
BY_ISO: dict[str, Country] = {c.iso2: c for c in COUNTRIES}


def by_code(code: int) -> Country | None:
    return BY_CODE.get(int(code))
