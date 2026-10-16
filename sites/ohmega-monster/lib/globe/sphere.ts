// Globe geometry primitives: unit-vector polylines on the sphere, the graticule, and the coastline loader. Pure TS, client-safe.
// (Extracted from components/GlobeSpinner.tsx so the spinner and the full-screen viewer share one implementation.)

export type Poly = Float32Array; // x, y, z triples on the unit sphere; z is toward the north pole
export const RAD = Math.PI / 180;
export const STEP = 3 * RAD; // longest straight piece before a segment is subdivided along the sphere

// Inline outline (Eurasia + Africa, the Americas, Australia), tolerance 8 degrees: enough to read as Earth on the first frame.
export const COARSE: number[][] = [
  [180, 69, 104, 78, 72, 66, 19, 70, 6, 59, 29, 60, 8, 57, -9, 37, 42, 42, 26, 40, 34, 31, -6, 36, -18, 15, 8, 5, 26, -34, 51, 11, 32, 30, 44, 13, 60, 22, 48, 30, 66, 25, 78, 8, 91, 23, 104, 1, 100, 13, 122, 28, 118, 39, 129, 35, 135, 55, 164, 63, 157, 51, 180, 65],
  [-123, 49, -147, 61, -165, 54, -157, 71, -94, 72, -81, 69, -92, 57, -56, 53, -80, 25, -97, 27, -82, 9, -35, -6, -68, -52, -78, 8, -112, 25, -123, 49],
  [126, -32, 115, -34, 114, -22, 132, -11, 154, -28, 146, -39, 126, -32],
];

export const vec = (lon: number, lat: number): [number, number, number] => {
  const a = lon * RAD, b = lat * RAD, c = Math.cos(b);
  return [c * Math.cos(a), c * Math.sin(a), Math.sin(b)];
};

/** [lon, lat, lon, lat, ...] lines to unit-vector polylines, long segments subdivided so they bend with the sphere. */
export function toPolys(lines: number[][]): Poly[] {
  return lines.map((l) => {
    const out: number[] = [];
    let prev: [number, number, number] | null = null;
    for (let i = 0; i + 1 < l.length; i += 2) {
      const v = vec(l[i], l[i + 1]);
      if (prev) {
        const ang = Math.acos(Math.min(1, Math.max(-1, prev[0] * v[0] + prev[1] * v[1] + prev[2] * v[2])));
        const n = Math.ceil(ang / STEP);
        for (let k = 1; k < n; k++) {
          const t = k / n;
          const x = prev[0] + (v[0] - prev[0]) * t, y = prev[1] + (v[1] - prev[1]) * t, z = prev[2] + (v[2] - prev[2]) * t;
          const h = Math.hypot(x, y, z) || 1;
          out.push(x / h, y / h, z / h);
        }
      }
      out.push(v[0], v[1], v[2]);
      prev = v;
    }
    return Float32Array.from(out);
  });
}

export function graticule(): Poly[] {
  const lines: number[][] = [];
  for (let lat = -60; lat <= 60; lat += 30) {
    const l: number[] = [];
    for (let lon = -180; lon <= 180; lon += 10) l.push(lon, lat);
    lines.push(l);
  }
  for (let lon = -180; lon < 180; lon += 30) {
    const l: number[] = [];
    for (let lat = -90; lat <= 90; lat += 10) l.push(lon, lat);
    lines.push(l);
  }
  return toPolys(lines);
}

export const GRAT = graticule();
export const COARSE_POLYS = toPolys(COARSE);
let landPolys: Poly[] | null = null;
let landPending: Promise<Poly[] | null> | null = null;

/** The detailed coastline, fetched once per page; null if it cannot be had (the inline outline stays). */
export function loadLand(): Promise<Poly[] | null> {
  if (landPolys) return Promise.resolve(landPolys);
  landPending ??= fetch("/geo/land-lite.json")
    .then((r) => (r.ok ? r.json() : null))
    .then((d: { lines?: number[][] } | null) => (landPolys = d?.lines?.length ? toPolys(d.lines) : null))
    .catch(() => null);
  return landPending;
}
