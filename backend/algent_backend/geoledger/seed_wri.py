"""
Seed the ledger with every power plant of the WRI Global Power Plant Database (CC BY 4.0, World Resources Institute).

The database is one CSV (about 35,000 plants: name, country, capacity in MW, latitude, longitude, primary fuel, owner,
commissioning year). It comes as a zip from WRI's data portal, or from a file the operator already has (``path``):
this module reads either. Positions are the database's own and stay ``approximate`` (some are surveyed, some are not, and the file does not say
which we can rely on); every asset carries source, licence and url, as CC BY 4.0 requires.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .contracts import Asset
from .store import Ledger

SOURCE = "WRI Global Power Plant Database v1.3"
LICENCE = "CC BY 4.0"
SOURCE_URL = "https://datasets.wri.org/dataset/globalpowerplantdatabase"
DOWNLOAD_URL = "https://wri-dataportal-prod.s3.amazonaws.com/manual/global_power_plant_database_v_1_3.zip"
_CSV_NAME = "global_power_plant_database.csv"


def fetch(url: str = DOWNLOAD_URL) -> bytes:
    """The zip's bytes (one polite request; the operator runs this knowingly via ``newsroom geo seed``)."""
    import httpx

    from algent_backend.polite_http import USER_AGENT

    resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=120.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def csv_text(blob: bytes) -> str:
    """The CSV inside a WRI zip, or the blob itself when it already is the CSV."""
    if blob[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            name = next((n for n in z.namelist() if n.endswith(_CSV_NAME)), None) or next(n for n in z.namelist() if n.endswith(".csv"))
            return z.read(name).decode("utf-8-sig")
    return blob.decode("utf-8-sig")


def _iso2() -> dict[str, str]:
    from algent_backend.actors import registry

    return {c.iso3: c.iso2 for c in registry.load().values()}


def _num(raw: str) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def rows_to_assets(text: str, iso2: dict[str, str] | None = None) -> Iterator[Asset]:
    iso2 = iso2 if iso2 is not None else _iso2()
    for row in csv.DictReader(io.StringIO(text)):
        lat, lon = _num(row.get("latitude", "")), _num(row.get("longitude", ""))
        gid, name = (row.get("gppd_idnr") or "").strip(), (row.get("name") or "").strip()
        if not gid or not name or lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        attrs: dict[str, Any] = {}
        if (mw := _num(row.get("capacity_mw", ""))) is not None:
            attrs["capacity_mw"] = round(mw, 1)
        if fuel := (row.get("primary_fuel") or "").strip():
            attrs["fuel"] = fuel
        if owner := (row.get("owner") or "").strip():
            attrs["owner"] = owner[:80]
        if (year := _num(row.get("commissioning_year", ""))) is not None:
            attrs["year"] = int(year)
        yield Asset(id=f"wri-{gid}", name=name, type="power_plant", country=iso2.get((row.get("country") or "").strip(), ""),
                    lat=round(lat, 5), lon=round(lon, 5), precision="approximate", attrs=attrs, source=SOURCE,
                    licence=LICENCE, source_url=SOURCE_URL, provenance="aggregated")


def seed(ledger: Ledger, *, path: Path | None = None, url: str = DOWNLOAD_URL) -> dict[str, int]:
    """Read the database (from ``path`` or the web) and append every plant not already on file."""
    blob = path.read_bytes() if path is not None else fetch(url)
    found = list(rows_to_assets(csv_text(blob)))
    added = ledger.add_assets(found)
    return {"read": len(found), "added": added, "unchanged": len(found) - added}
