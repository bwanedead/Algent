"""
Classifying what a position report is — ship class from the AIS ship-type code, flag state from the MMSI's country
prefix (ITU "MID"), aircraft id. Pure tables and functions; nothing here fetches.

Flag state is the country the vessel is REGISTERED to by its radio identity (flags of convenience are visible as such:
a Greek-owned tanker flying Liberia shows Liberia). Unknown prefixes give "".
"""

from __future__ import annotations

import zlib

#: Order matters: the snapshot stores the index, the site maps it back to a name and a colour.
VESSEL_CLASSES = ("tanker", "cargo", "passenger", "fishing", "military", "other")


def vessel_class(ship_type: int | None) -> int:
    """AIS ship type -> index into VESSEL_CLASSES. 80-89 tanker, 70-79 cargo, 60-69 passenger, 30 fishing,
    35 military and 55 law enforcement ('military'); unknown or anything else is 'other'."""
    t = ship_type or 0
    return 0 if 80 <= t <= 89 else 1 if 70 <= t <= 79 else 2 if 60 <= t <= 69 else 3 if t == 30 else 4 if t in (35, 55) else 5


_MID = {
    "AL": "201", "AD": "202", "AT": "203", "BE": "205", "BY": "206", "BG": "207", "CY": "209,210,212", "DE": "211,218",
    "GE": "213", "MD": "214", "MT": "215,229,248,249,256", "AM": "216", "DK": "219,220", "ES": "224,225", "FR": "226,227,228,501",
    "FI": "230", "FO": "231", "GB": "232,233,234,235", "GI": "236", "GR": "237,239,240,241", "HR": "238", "MA": "242",
    "HU": "243", "NL": "244,245,246", "IT": "247", "IE": "250", "IS": "251", "LI": "252", "LU": "253", "MC": "254",
    "PT": "204,255,263", "NO": "257,258,259", "PL": "261", "ME": "262", "RO": "264", "SE": "265,266", "SK": "267",
    "CH": "269", "CZ": "270", "TR": "271", "UA": "272", "RU": "273", "MK": "274", "LV": "275", "EE": "276", "LT": "277",
    "SI": "278", "RS": "279", "AI": "301", "AG": "304,305", "AW": "307", "BS": "308,309,311", "BM": "310", "BZ": "312",
    "BB": "314", "CA": "316", "KY": "319", "CR": "321", "CU": "323", "DM": "325", "DO": "327", "GD": "330", "GL": "331",
    "GT": "332", "HN": "334", "HT": "336", "US": "303,338,366,367,368,369", "JM": "339", "KN": "341", "LC": "343",
    "MX": "345", "NI": "350", "PA": "351,352,353,354,355,356,357,370,371,372,373,374", "PR": "358", "SV": "359",
    "TT": "362", "TC": "364", "VC": "375,376,377", "VG": "378", "VI": "379", "AF": "401", "SA": "403", "BD": "405",
    "BH": "408", "BT": "410", "CN": "412,413,414", "TW": "416", "LK": "417", "IN": "419", "IR": "422", "AZ": "423",
    "IQ": "425", "IL": "428", "JP": "431,432", "TM": "434", "KZ": "436", "UZ": "437", "JO": "438", "KR": "440,441",
    "KP": "445", "KW": "447", "LB": "450", "KG": "451", "MO": "453", "MV": "455", "MN": "457", "NP": "459", "OM": "461",
    "PK": "463", "QA": "466", "SY": "468", "AE": "470,471", "TJ": "472", "YE": "473,475", "HK": "477", "BA": "478",
    "AU": "503", "MM": "506", "BN": "508", "FM": "510", "PW": "511", "NZ": "512", "KH": "514,515", "FJ": "520",
    "ID": "525", "KI": "529", "LA": "531", "MY": "533", "MH": "538", "NC": "540", "PF": "546", "PH": "548", "PG": "553",
    "SB": "557", "WS": "561", "SG": "563,564,565,566", "TH": "567", "TO": "570", "TV": "572", "VN": "574", "VU": "576,577",
    "ZA": "601", "AO": "603", "DZ": "605", "BJ": "610", "BW": "611", "CM": "613", "CG": "615", "KM": "616,620", "CV": "617",
    "CI": "619", "DJ": "621", "EG": "622", "ET": "624", "ER": "625", "GA": "626", "GH": "627", "GM": "629", "GN": "632",
    "KE": "634", "LR": "636,637", "LY": "642", "MU": "645", "MG": "647", "ML": "649", "MZ": "650", "MR": "654", "NG": "657",
    "NA": "659", "SN": "663", "SC": "664", "SO": "666", "SL": "667", "ST": "668", "TG": "671", "TN": "672", "TZ": "674,677",
    "AR": "701", "BR": "710", "BO": "720", "CL": "725", "CO": "730", "EC": "735", "GY": "750", "PY": "755", "PE": "760",
    "SR": "765", "UY": "770", "VE": "775",
}
_BY_MID = {mid: iso for iso, mids in _MID.items() for mid in mids.split(",")}


def flag_of(mmsi: int) -> str:
    """ISO-2 flag state from a 9-digit ship MMSI ('' for other identities: aids to navigation, SAR craft, unknown prefixes)."""
    s = str(mmsi)
    return _BY_MID.get(s[:3], "") if len(s) == 9 and s[0] in "2345678" else ""


def aircraft_id(icao_hex: str) -> int:
    """A stable public handle for an aircraft (a hash of its ICAO address; the address itself and the registration are not published)."""
    return zlib.crc32(("ohmega:" + (icao_hex or "").lower()).encode()) & 0x7FFFFFFF
