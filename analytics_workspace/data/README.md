# Analytics basemap data

Downloaded locally (gitignored) by `scripts/download_basemap.py`.

| File | What | Size |
|------|------|------|
| `natural_earth/ne_110m_admin_0_countries.geojson` | Natural Earth **110m** admin-0 countries | ~1–2 MB |

This is a **coarse cultural outline** for country/theater maps — not high-res admin-1,
not elevation, not global tiles. Re-download anytime; never commit the geojson.

```powershell
.\.venv\Scripts\python.exe scripts\download_basemap.py
```
