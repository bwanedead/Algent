"""
Imagery sources, both keyless (verified 2026-10: no key, no token).

* **Sentinel-2 L2A** (Copernicus / ESA) through Microsoft's Planetary Computer: the STAC search (``/api/stac/v1/search``) finds scenes over a point
  with the tile's cloud cover; the data API (``/api/data/v1/item/bbox/...png``) renders a small PNG of a bbox from named bands, so no raster is
  downloaded. Two renders per scene: true colour (B04, B03, B02 with one FIXED stretch, so two dates are comparable) and the scene
  classification band (SCL) whose classes give the chip's OWN cloud, shadow and no-data share, not just the tile's.
* **NASA GIBS** WMS: VIIRS day/night band, gap-filled and lunar/BRDF corrected, daily, ~4 days behind: night lights.

``Imagery`` is the seam the pass talks to; tests substitute a fake with the same four methods. Every request goes through ``polite_http``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from algent_backend import polite_http

from . import flags

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
DATA_URL = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox/{w},{s},{e},{n}/{px}x{px}.png"
GIBS_URL = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
NIGHT_LAYER = "VIIRS_NOAA20_GapFilled_BRDF_Corrected_DayNightBand_Radiance"
COLLECTION = "sentinel-2-l2a"
#: The fixed stretch of surface reflectance (x10000) to 8 bit: the same for every date, so a difference is the ground, not the contrast stretch.
RESCALE = "0,3000"

BBox = tuple[float, float, float, float]   # west, south, east, north


@dataclass(frozen=True)
class Scene:
    id: str
    date: str                  # YYYY-MM-DD (acquisition)
    datetime: str
    tile_cloud: float          # the whole tile's cloud cover, % (as the provider reports it)


class Imagery(Protocol):
    def search(self, bbox: BBox, start: str, end: str) -> list[Scene]: ...
    def rgb(self, scene: Scene, bbox: BBox) -> bytes: ...
    def scl(self, scene: Scene, bbox: BBox) -> bytes: ...
    def night(self, bbox: BBox, day: str) -> bytes: ...


class PlanetaryComputer:
    """Sentinel-2 via Planetary Computer, night lights via GIBS."""

    def search(self, bbox: BBox, start: str, end: str) -> list[Scene]:
        w, s, e, n = bbox
        body: dict[str, Any] = {"collections": [COLLECTION], "intersects": {"type": "Point", "coordinates": [(w + e) / 2, (s + n) / 2]},
                                "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": 40,
                                "query": {"eo:cloud_cover": {"lt": flags.TILE_CLOUD_PREFILTER}}, "sortby": [{"field": "datetime", "direction": "desc"}]}
        data = polite_http.post_json(STAC_URL, body)
        out = []
        for f in data.get("features", []):
            p = f.get("properties", {})
            dt = str(p.get("datetime", ""))
            if f.get("id") and dt:
                out.append(Scene(str(f["id"]), dt[:10], dt, float(p.get("eo:cloud_cover", 100.0))))
        return out

    def _chip(self, scene: Scene, bbox: BBox, assets: list[str], extra: dict[str, Any]) -> bytes:
        w, s, e, n = bbox
        url = DATA_URL.format(w=w, s=s, e=e, n=n, px=flags.CHIP_PX)
        return polite_http.get_bytes(url, {"collection": COLLECTION, "item": scene.id, "assets": assets, **extra})

    def rgb(self, scene: Scene, bbox: BBox) -> bytes:
        return self._chip(scene, bbox, ["B04", "B03", "B02"], {"rescale": RESCALE, "color_formula": "gamma RGB 1.8"})

    def scl(self, scene: Scene, bbox: BBox) -> bytes:
        return self._chip(scene, bbox, ["SCL"], {"rescale": "0,11", "resampling": "nearest"})

    def night(self, bbox: BBox, day: str) -> bytes:
        w, s, e, n = bbox
        return polite_http.get_bytes(GIBS_URL, {"SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.1.1", "LAYERS": NIGHT_LAYER, "STYLES": "",
                                                "SRS": "EPSG:4326", "BBOX": f"{w},{s},{e},{n}", "WIDTH": flags.NIGHT_PX, "HEIGHT": flags.NIGHT_PX,
                                                "FORMAT": "image/png", "TIME": day, "TRANSPARENT": "FALSE"})
