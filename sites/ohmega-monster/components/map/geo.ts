// Pure geometry for the interactive maps: our equirectangular frame specs (daily/dossier `TheaterMap`, the /live
// `world.json`) turned into lon/lat and GeoJSON. Client-safe: types only from lib, no server imports.

export type LngLat = [number, number];
export type Props = Record<string, string | number | boolean | null>;
export type Feature = { type: "Feature"; properties: Props; geometry: { type: "Point"; coordinates: LngLat } | { type: "LineString"; coordinates: LngLat[] } | { type: "Polygon"; coordinates: LngLat[][] } };
export type FeatureCollection = { type: "FeatureCollection"; features: Feature[] };
/** A frame in lon/lat: [west, south, east, north]. */
export type Bounds = [number, number, number, number];

export const collection = (features: Feature[]): FeatureCollection => ({ type: "FeatureCollection", features });
export const pointFeature = (at: LngLat, properties: Props): Feature => ({ type: "Feature", properties, geometry: { type: "Point", coordinates: at } });

/** A frame spec's x/y (0..width, 0..height) back to lon/lat. Exact: the frame is equirectangular. */
export function unproject(frame: { bbox: number[]; width: number; height: number }, x: number, y: number): LngLat {
  const [w, s, e, n] = frame.bbox;
  return [w + (x / frame.width) * (e - w), n - (y / frame.height) * (n - s)];
}

/** The closed rings of an SVG path made only of M/L/Z (what the backend writes), as lon/lat. Malformed text yields []. */
export function pathRings(d: string, frame: { bbox: number[]; width: number; height: number }): LngLat[][] {
  const rings: LngLat[][] = [];
  for (const part of d.split("M").slice(1)) {
    const pts: LngLat[] = [];
    for (const pair of part.replace(/Z\s*$/, "").split("L")) {
      const [x, y] = pair.trim().split(/[\s,]+/).map(Number);
      if (Number.isFinite(x) && Number.isFinite(y)) pts.push(unproject(frame, x, y));
    }
    if (pts.length >= 3) rings.push([...pts, pts[0]]);
  }
  return rings;
}

/** A polygon feature per ring (rings of one country are separate parts; holes are rare at the world scale). */
export function ringFeatures(rings: LngLat[][], properties: Props): Feature[] {
  return rings.map((r) => ({ type: "Feature", properties, geometry: { type: "Polygon", coordinates: [r] } }));
}

/** [west, south, east, north] of a set of coordinates, or null when empty. */
export function boundsOf(points: LngLat[]): Bounds | null {
  if (points.length === 0) return null;
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  for (const [x, y] of points) {
    if (x < w) w = x;
    if (x > e) e = x;
    if (y < s) s = y;
    if (y > n) n = y;
  }
  return [w, s, e, n];
}

/** A representative point for a feature: the point itself, a line's midpoint vertex, a polygon's bounding-box centre. */
export function anchorOf(f: Feature): LngLat {
  const g = f.geometry;
  if (g.type === "Point") return g.coordinates;
  const pts = g.type === "LineString" ? g.coordinates : g.coordinates[0];
  if (g.type === "LineString") return pts[Math.floor(pts.length / 2)];
  const b = boundsOf(pts) as Bounds;
  return [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
}

/** Zoom-appropriate padding rule: the frame is already padded by the backend, so this is only a safe inset. */
export const FIT_PADDING = { top: 28, right: 28, bottom: 28, left: 28 };
