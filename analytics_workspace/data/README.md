# Analytics basemap data

Downloaded locally (gitignored) by `scripts/download_basemap.py`.

| File | What | Size |
|------|------|------|
| `natural_earth/ne_110m_admin_0_countries.geojson` | Natural Earth **110m** admin-0 countries | ~1–2 MB |
| `natural_earth/ne_50m_admin_0_countries.geojson` | 50m countries (daily-map drawing + validation) | 3.1 MB |
| `natural_earth/ne_10m_populated_places_simple.geojson` | reference cities, capitals | 4.9 MB |
| `natural_earth/ne_50m_rivers_lake_centerlines.geojson` | rivers | 0.8 MB |
| `natural_earth/ne_50m_lakes.geojson` | lakes | 0.9 MB |

This is a **coarse cultural outline** for country/theater maps — not high-res admin-1,
not elevation, not global tiles. Re-download anytime; never commit the geojson.

```powershell
.\.venv\Scripts\python.exe scripts\download_basemap.py
```
