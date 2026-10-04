"""Download the Natural Earth basemap layers (public domain) as GeoJSON into data/natural_earth/.

Layers (the 110m file is the always-available fallback; the rest draw the daily maps):
  110m_countries   admin-0 countries           validation + fallback drawing
  50m_countries    admin-0 countries           drawing (borders readable at theatre zoom)
  10m_places       populated places (simple)   reference cities and capitals
  50m_rivers       rivers + lake centerlines   rivers
  50m_lakes        lakes                       lakes
Water is drawn as the map background (no ocean polygon needed). Sizes are printed on download and
recorded in docs/architecture/map-analytics-stack.md.

Usage: python download_basemap.py [--only 110m_countries,50m_countries,...]
Re-run anytime; each file is overwritten. Not planet tiles, not elevation, not OSM dumps.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "natural_earth"
_BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"

# key -> (file name, minimum feature count for a sanity check)
LAYERS = {
    "110m_countries": ("ne_110m_admin_0_countries.geojson", 50),
    "50m_countries": ("ne_50m_admin_0_countries.geojson", 150),
    "10m_places": ("ne_10m_populated_places_simple.geojson", 1000),
    "50m_rivers": ("ne_50m_rivers_lake_centerlines.geojson", 100),
    "50m_lakes": ("ne_50m_lakes.geojson", 50),
}


def fetch(key: str) -> bool:
    name, minimum = LAYERS[key]
    url = _BASE + name
    print(f"downloading {key}\n  {url}")
    try:
        with urllib.request.urlopen(url, timeout=180) as resp:
            raw = resp.read()
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  failed: {exc}", file=sys.stderr)
        return False
    if data.get("type") != "FeatureCollection" or len(data.get("features") or []) < minimum:
        print("  unexpected geojson shape", file=sys.stderr)
        return False
    (OUT_DIR / name).write_bytes(raw)
    print(f"  wrote {name} ({len(raw):,} bytes, {len(data['features'])} features)")
    return True


def main(argv: list[str]) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    keys = list(LAYERS)
    if "--only" in argv:
        keys = [k for k in argv[argv.index("--only") + 1].split(",") if k in LAYERS]
    return 0 if all([fetch(k) for k in keys]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
