// Country polygons for the globe: loads /geo/countries-lite.json (built by analytics_workspace/scripts/make_countries_lite.py from
// Natural Earth 110m, ~110 KB) and prepares it for drawing (unit-vector rings) and for hit tests (lon/lat rings, plain ray casting).
// Pure TS, client-safe.

import { buildRings } from "./clip";
import { toPolys, type Poly } from "./sphere";

type RawCountry = { iso: string; name: string; rings: number[][] };
type Raw = { v: number; countries: RawCountry[]; borders: number[][]; coast: number[][] };

export type Country = {
  iso: string; //     ISO 3166 alpha-2 ("" for the two unrecognised territories)
  name: string;
  rings: number[][]; // lon, lat, lon, lat ... (outer rings), for hit tests
  bbox: [number, number, number, number]; // west, south, east, north of the rings
  fill: Poly[]; //    the same rings as closed, wound unit-vector rings for lib/globe/clip.ts landPath
};

export type Countries = {
  list: Country[];
  /** Edges shared by two countries, as polylines for `paths`. */
  borders: Poly[];
  /** Coast edges (the map's own seams removed), as polylines for `paths`. */
  coast: Poly[];
};

function prepare(raw: Raw): Countries {
  const list = raw.countries.map((c): Country => {
    let w = 180, s = 90, e = -180, n = -90;
    for (const r of c.rings) for (let i = 0; i + 1 < r.length; i += 2) { w = Math.min(w, r[i]); e = Math.max(e, r[i]); s = Math.min(s, r[i + 1]); n = Math.max(n, r[i + 1]); }
    const closed = c.rings.map((r) => [...r, r[0], r[1]]);
    return { iso: c.iso, name: c.name, rings: c.rings, bbox: [w, s, e, n], fill: buildRings(toPolys(closed)) };
  });
  return { list, borders: toPolys(raw.borders), coast: toPolys(raw.coast) };
}

let loaded: Countries | null = null;
let pending: Promise<Countries | null> | null = null;

/** The country set, fetched once per page; null if it cannot be had (the plain land layers stay). */
export function loadCountries(): Promise<Countries | null> {
  if (loaded) return Promise.resolve(loaded);
  pending ??= fetch("/geo/countries-lite.json")
    .then((r) => (r.ok ? r.json() : null))
    .then((d: Raw | null) => (loaded = d?.countries?.length ? prepare(d) : null))
    .catch(() => null);
  return pending;
}

function inRing(r: number[], lon: number, lat: number): boolean {
  let inside = false;
  for (let i = 0, j = r.length - 2; i < r.length; j = i, i += 2) {
    const xi = r[i], yi = r[i + 1], xj = r[j], yj = r[j + 1];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** The country containing a point, or null (open sea, or a place too small for the 110m outline). */
export function countryAt(cs: Countries, lon: number, lat: number): Country | null {
  for (const c of cs.list) {
    const [w, s, e, n] = c.bbox;
    if (lon < w || lon > e || lat < s || lat > n) continue;
    if (c.rings.some((r) => inRing(r, lon, lat))) return c;
  }
  return null;
}

/** Middle of a country's bounding box (good enough to fly to; the shape is not needed). */
export const centroidOf = (c: Country): { lon: number; lat: number } => ({ lon: (c.bbox[0] + c.bbox[2]) / 2, lat: (c.bbox[1] + c.bbox[3]) / 2 });
