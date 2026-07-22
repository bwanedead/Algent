"""Download Natural Earth 110m admin-0 countries as GeoJSON (tiny cultural basemap).

~1–2 MB. Not planet tiles, not elevation, not OSM dumps.
Re-run anytime; overwrites data/natural_earth/ne_110m_admin_0_countries.geojson.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "natural_earth"
OUT_GEOJSON = OUT_DIR / "ne_110m_admin_0_countries.geojson"

# Same Natural Earth 110m cultural layer, geojson form (small).
_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_110m_admin_0_countries.geojson"
)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"downloading NE 110m admin-0 countries …\n  {_URL}")
    try:
        with urllib.request.urlopen(_URL, timeout=90) as resp:
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001
        print(f"download failed: {exc}", file=sys.stderr)
        return 1
    print(f"  got {len(raw):,} bytes")
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        print(f"invalid json: {exc}", file=sys.stderr)
        return 1
    if data.get("type") != "FeatureCollection" or len(data.get("features") or []) < 50:
        print("unexpected geojson shape", file=sys.stderr)
        return 1
    OUT_GEOJSON.write_bytes(raw)
    print(f"wrote {OUT_GEOJSON} ({OUT_GEOJSON.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
