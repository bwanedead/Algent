"use client";

// The live objects near one theater, fetched the bandwidth-efficient way /live uses at map zoom (see useLiveEntities.ts): the small
// `tiles/index` document, then only the 10-degree tiles that intersect the theater's box (plus a small margin), and the rows are cut to that box, each refetched only when its etag changed.
// Rows are decoded with /live's own decoders and reduced at once to the three kinds the daily shows (theaterObjects.groupOf), so a cached
// tile holds a handful of objects, not the thousands of ships in it. Polls every POLL_MS, and only while `host` is near the viewport and the
// tab is visible; leaving the page area stops the clock, coming back loads at once.

import { useEffect, useRef, useState, type RefObject } from "react";

import { fetchSnapshot, type TileDoc, type TilesIndex, type VesselsDoc, type AircraftDoc } from "@/lib/live-shared";

import { decodeAircraft, decodeVessels } from "./entities";
import { groupOf, NO_OBJECTS, shape, withMargin, type Obj, type Shaped } from "./theaterObjects";
import { tilesIn } from "./useLiveEntities";

const POLL_MS = 60_000;
const NEAR_PX = 600; // start loading this far before the strip scrolls into view
type Cached = { etag: string; objs: Obj[] };
const LAYERS = [["vessels", "v"], ["aircraft", "a"]] as const;

/** The tile ids to read for `box`: every tile that intersects it (rows are then filtered to the box itself). */
const pickTiles = (box: [number, number, number, number], deg: number): string[] =>
  tilesIn([Math.max(-180, box[0]), Math.max(-90, box[1]), Math.min(180, box[2]), Math.min(90, box[3])], deg);

async function fetchObjects(box: [number, number, number, number], cache: Map<string, Cached>): Promise<Obj[] | null> {
  const index = await fetchSnapshot<TilesIndex>("tiles/index");
  if (!index) return null;
  const ids = pickTiles(box, index.deg);
  const keep = new Set<string>();
  const jobs: Promise<void>[] = [];
  for (const [layer, folder] of LAYERS) {
    for (const id of ids) {
      const entry = index[layer][id];
      if (!entry) continue;
      const key = `${folder}/${id}`;
      keep.add(key);
      if (cache.get(key)?.etag === entry[1]) continue;
      jobs.push(fetchSnapshot<TileDoc>(`tiles/${key}`).then((t) => {
        if (!t) return;
        const ents = layer === "vessels" ? decodeVessels({ rows: t.rows } as VesselsDoc) : decodeAircraft({ rows: t.rows } as AircraftDoc);
        const objs: Obj[] = [];
        for (const e of ents) {
          const group = groupOf(e);
          if (group) objs.push({ group, e });
        }
        cache.set(key, { etag: entry[1], objs });
      }));
    }
  }
  await Promise.all(jobs);
  for (const key of Array.from(cache.keys())) if (!keep.has(key)) cache.delete(key);
  const inBox = (o: Obj) => o.e.lon >= box[0] && o.e.lon <= box[2] && o.e.lat >= box[1] && o.e.lat <= box[3];
  return Array.from(keep).flatMap((k) => cache.get(k)?.objs ?? []).filter(inBox);
}

/** The military aircraft, tankers and military vessels inside `bbox` (plus a margin), refreshed while `host` is on screen. */
export function useTheaterObjects(bbox: number[] | null | undefined, host: RefObject<Element | null>): Shaped {
  const key = bbox && bbox.length === 4 && bbox.every(Number.isFinite) ? bbox.join(",") : "";
  const [state, setState] = useState<Shaped>(NO_OBJECTS);
  const [near, setNear] = useState(false);
  const cache = useRef(new Map<string, Cached>());

  useEffect(() => {
    const el = host.current;
    if (!el || !key || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((entries) => setNear(entries.some((e) => e.isIntersecting)), { rootMargin: `${NEAR_PX}px` });
    io.observe(el);
    return () => io.disconnect();
  }, [host, key]);

  useEffect(() => {
    if (!key || !near) return;
    const box = withMargin(key.split(",").map(Number));
    let alive = true;
    let busy = false;
    let last = 0;
    const run = async () => {
      if (busy) return;
      busy = true;
      last = Date.now();
      try {
        const all = await fetchObjects(box, cache.current);
        if (alive && all) setState(shape(all));
      } finally {
        busy = false;
      }
    };
    void run();
    const timer = setInterval(() => { if (!document.hidden) void run(); }, POLL_MS);
    const back = () => { if (!document.hidden && Date.now() - last >= POLL_MS) void run(); };
    document.addEventListener("visibilitychange", back);
    return () => {
      alive = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", back);
    };
  }, [key, near]);

  useEffect(() => { cache.current.clear(); }, [key]);

  return state;
}
