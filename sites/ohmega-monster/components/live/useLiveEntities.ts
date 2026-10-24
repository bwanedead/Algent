"use client";

// Where the /live map's ships and aircraft come from, chosen by what the view needs (a minute of bandwidth per open tab is the cost):
//   - "points": zoomed out (below DOT_ZOOM) only the heat glow shows, so the compact `points` document (every object's real position
//     rounded to 0.05 degree + class, ~30 KB gz) feeds it, exactly as the full rows would;
//   - "tiles": from DOT_ZOOM the dots and icons need the real rows, but only for what the (padded) viewport covers: the 10-degree
//     tiles under it, each refetched only when its etag in `tiles/index` changed;
//   - "full": the whole snapshots, when a filter needs fields the other two do not carry (flag, search text, speed, notable) or when
//     the new documents are missing (an older backend).
// Polls every POLL_MS; not while the tab is hidden or the map is off screen. Entities are the same objects the full snapshot decodes to.

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchSnapshot, type AircraftDoc, type PointsDoc, type TileDoc, type TilesIndex, type VesselsDoc } from "@/lib/live-shared";

import { decodeAircraft, decodePoints, decodeVessels, type Entity, type Kind } from "./entities";
import { DOT_ZOOM, type Tracks } from "./TrackLayers";

const POLL_MS = 180_000; // the stream republishes every 3 min (backend live/flags.py R2_SNAPSHOT_SECONDS): polling faster only re-reads the same object
const MOVE_DEBOUNCE_MS = 250;

export type LayerMeta = { n: number; counts: Record<string, number>; as_of: string };
export type FeedMode = "points" | "tiles" | "full";
type LayerName = "vessels" | "aircraft";
const FOLDER: Record<LayerName, string> = { vessels: "v", aircraft: "a" };
const KIND: Record<LayerName, Kind> = { vessels: "ship", aircraft: "air" };

type Cached = { etag: string; ents: Entity[] };

/** Tile ids (`r<row>c<col>`, row-major from the south-west corner, as the backend names them) covering `box`. */
export function tilesIn(box: [number, number, number, number], deg: number): string[] {
  const rows = Math.floor(180 / deg);
  const cols = Math.floor(360 / deg);
  const at = (v: number, max: number) => Math.min(max - 1, Math.max(0, Math.floor(v)));
  const [r0, r1] = [at((box[1] + 90) / deg, rows), at((box[3] + 90) / deg, rows)];
  const [c0, c1] = [at((box[0] + 180) / deg, cols), at((box[2] + 180) / deg, cols)];
  const out: string[] = [];
  for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) out.push(`r${String(r).padStart(2, "0")}c${String(c).padStart(2, "0")}`);
  return out;
}

export function useLiveEntities(tracks: Tracks, needFull: boolean, want: { ships: boolean; air: boolean }) {
  const [ships, setShips] = useState<Entity[]>([]);
  const [planes, setPlanes] = useState<Entity[]>([]);
  const [meta, setMeta] = useState<{ vessels: LayerMeta | null; aircraft: LayerMeta | null }>({ vessels: null, aircraft: null });
  const [topFlags, setTopFlags] = useState<[string, number][]>([]);
  const [mode, setMode] = useState<FeedMode>("points");

  const opts = useRef({ needFull, want });
  opts.current = { needFull, want };
  const degraded = useRef(false); // points or tiles missing: stay on the full snapshots
  const gen = useRef(0);
  const lastMode = useRef<FeedMode | null>(null);
  const lastLoad = useRef(0);
  const points = useRef<PointsDoc | null>(null);
  const index = useRef<TilesIndex | null>(null);
  const tiles = useRef<Map<string, Cached>>(new Map());

  const load: (force: boolean) => Promise<void> = useCallback(async (force: boolean): Promise<void> => {
    const my = ++gen.current;
    const view = tracks.view();
    const o = opts.current;
    const next: FeedMode = o.needFull || degraded.current ? "full" : !view || view.zoom < DOT_ZOOM ? "points" : "tiles";
    const refresh = force || next !== lastMode.current;
    lastMode.current = next;
    lastLoad.current = Date.now();
    const done = (m: FeedMode) => { if (gen.current === my) setMode(m); };
    const give = (v: Entity[] | null, a: Entity[] | null, mv: LayerMeta | null, ma: LayerMeta | null) => {
      if (gen.current !== my) return;
      if (v) setShips(v);
      if (a) setPlanes(a);
      setMeta((m) => ({ vessels: mv ?? m.vessels, aircraft: ma ?? m.aircraft }));
    };

    if (next === "full") {
      const [v, a] = await Promise.all([fetchSnapshot<VesselsDoc>("vessels"), fetchSnapshot<AircraftDoc>("aircraft")]);
      give(v ? decodeVessels(v) : null, a ? decodeAircraft(a) : null, v && { n: v.n, counts: v.counts, as_of: v.as_of }, a && { n: a.n, counts: a.counts, as_of: a.as_of });
      return done("full");
    }

    if (next === "points") {
      if (refresh || !points.current) points.current = await fetchSnapshot<PointsDoc>("points");
      const p = points.current;
      if (!p) { degraded.current = true; return void load(true); }
      const lv = p.layers.vessels;
      const la = p.layers.aircraft;
      give(decodePoints(lv, "ship"), decodePoints(la, "air"), { n: lv.n, counts: lv.counts, as_of: p.as_of }, { n: la.n, counts: la.counts, as_of: p.aircraft_as_of });
      if (gen.current === my) setTopFlags(lv.flags ?? []);
      return done("points");
    }

    if (refresh || !index.current) index.current = await fetchSnapshot<TilesIndex>("tiles/index");
    const idx = index.current;
    if (!idx || !view) { degraded.current = true; return void load(true); }
    const ids = tilesIn([Math.max(-180, view.box[0]), Math.max(-90, view.box[1]), Math.min(180, view.box[2]), Math.min(90, view.box[3])], idx.deg);
    const jobs: Promise<void>[] = [];
    const keep = new Set<string>();
    for (const name of ["vessels", "aircraft"] as LayerName[]) {
      if (!(name === "vessels" ? o.want.ships : o.want.air)) continue;
      for (const id of ids) {
        const entry = idx[name][id];
        if (!entry) continue;
        const key = `${FOLDER[name]}/${id}`;
        keep.add(key);
        if (tiles.current.get(key)?.etag === entry[1]) continue;
        jobs.push(fetchSnapshot<TileDoc>(`tiles/${key}`).then((t) => {
          if (t) tiles.current.set(key, { etag: entry[1], ents: name === "vessels" ? decodeVessels({ rows: t.rows } as VesselsDoc) : decodeAircraft({ rows: t.rows } as AircraftDoc) });
        }));
      }
    }
    await Promise.all(jobs);
    for (const key of Array.from(tiles.current.keys())) if (!keep.has(key)) tiles.current.delete(key);
    const gather = (name: LayerName) => Array.from(keep).filter((k) => k.startsWith(`${FOLDER[name]}/`)).flatMap((k) => tiles.current.get(k)?.ents ?? []);
    const sum = (name: LayerName, asOf: string): LayerMeta => ({
      n: Object.values(idx[name]).reduce((t, e) => t + e[0], 0), counts: points.current?.layers[name].counts ?? {}, as_of: asOf, // class counts: as of the last points load
    });
    give(o.want.ships ? gather("vessels") : null, o.want.air ? gather("aircraft") : null, sum("vessels", idx.as_of), sum("aircraft", idx.aircraft_as_of));
    done("tiles");
  }, [tracks]);

  // A different need (filter on or off, a layer switched) or a first load.
  useEffect(() => { void load(false); }, [load, needFull, want.ships, want.air]);

  // The view changed: maybe another mode, maybe other tiles.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    tracks.onMove = () => { clearTimeout(timer); timer = setTimeout(() => void load(false), MOVE_DEBOUNCE_MS); };
    return () => { clearTimeout(timer); tracks.onMove = null; };
  }, [tracks, load]);

  // The minute poll: not while the tab is hidden or the map is off screen.
  useEffect(() => {
    const due = () => !document.hidden && tracks.isOnScreen();
    const id = setInterval(() => { if (due()) void load(true); }, POLL_MS);
    const back = () => { if (due() && Date.now() - lastLoad.current >= POLL_MS) void load(true); };
    document.addEventListener("visibilitychange", back);
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", back); };
  }, [tracks, load]);

  return { ships, planes, meta, topFlags, mode };
}
