"use client";

// The /live map's data, fetched as little as possible (Supabase egress is the scarce resource; docs/guides/worker-server.md "Live feeds"):
//
//   * Every minute (≥ 60 s): `summary` and the world `density` grid (a few tens of KB gzipped, revalidated: an unchanged one is a 304).
//     Far out, that is all the map draws: shaded cells, no objects.
//   * From DOT_ZOOM on: the tile index, then ONLY the object tiles under the view (+ a margin), each refetched only when its etag moved.
//     Panning refetches nothing already cached; tiles leaving the view are forgotten.
//   * Nothing is polled while the tab is hidden or the map is off screen; coming back refreshes at once if the data is over a minute old.
//   * Trails are not here: they are fetched on demand (trails.ts). Fire heat and receiver coverage are slow (every 10 minutes).
//   * Old deployments (no `density` document): falls back to the full `vessels` / `aircraft` snapshots, re-probing for the new layout
//     on every poll, so the switch happens by itself when the backend starts writing it.
//
// Client-only; imports no server module.

import { useEffect, useState, type RefObject } from "react";

import {
  fetchSnapshot, type AircraftDoc, type CoverageDoc, type DensityDoc, type FiresDoc, type Summary, type TileDoc, type TileIndex, type VesselsDoc,
} from "@/lib/live-shared";

import { decodeAircraft, decodeVessels, type Entity } from "./entities";
import { TileCache, wantedTiles } from "./tileFeed";
import { DOT_ZOOM, type Tracks } from "./TrackLayers";

const POLL_MS = 60_000;
const SLOW_MS = 600_000;
const VIEW_DEBOUNCE_MS = 400;

export type Totals = { n: number; counts: Record<string, number>; as_of: string };
export type LiveFeed = {
  summary: Summary | null;
  /** Objects loaded now: the whole world with the old layout, only the tiles under the view with the tiled one. */
  ships: Entity[];
  planes: Entity[];
  totals: { ships: Totals | null; air: Totals | null };
  /** True with the tiled layout: far out the map holds density only, so object filters and search reach only what is loaded. */
  tiled: boolean;
  fires: FiresDoc | null;
  coverage: CoverageDoc | null;
};

export function useLiveFeed(tracks: Tracks, wrap: RefObject<HTMLElement>, summary0: Summary | null): LiveFeed {
  const [summary, setSummary] = useState<Summary | null>(summary0);
  const [ships, setShips] = useState<Entity[]>([]);
  const [planes, setPlanes] = useState<Entity[]>([]);
  const [totals, setTotals] = useState<LiveFeed["totals"]>({ ships: null, air: null });
  const [tiled, setTiled] = useState(false);
  const [fires, setFires] = useState<FiresDoc | null>(null);
  const [coverage, setCoverage] = useState<CoverageDoc | null>(null);

  useEffect(() => {
    let dead = false;
    let onscreen = typeof IntersectionObserver === "undefined";
    let isTiled = false;
    let lastPoll = 0;
    let lastSlow = 0;
    const shipCache = new TileCache("vessels", (n, o) => fetchSnapshot<TileDoc>(n, o), decodeVessels);
    const airCache = new TileCache("aircraft", (n, o) => fetchSnapshot<TileDoc>(n, o), decodeAircraft);

    const active = () => !dead && !document.hidden && onscreen;

    // ---- tiles under the view ----------------------------------------------------------------------------------------------
    const syncTiles = async () => {
      const view = tracks.view();
      if (!view || view.zoom < DOT_ZOOM) {
        if (shipCache.clear()) setShips([]);
        if (airCache.clear()) setPlanes([]);
        return;
      }
      const index = await fetchSnapshot<TileIndex>("tiles/index");
      if (dead || !index) return;
      const b = (tracks.view() ?? view).bounds; // the view may have moved while the index downloaded
      const ws = wantedTiles(index, "vessels", b), wa = wantedTiles(index, "aircraft", b);
      const [cs, ca] = await Promise.all([shipCache.sync(index, ws), airCache.sync(index, wa)]);
      if (dead) return;
      if (cs) setShips(shipCache.entities(ws));
      if (ca) setPlanes(airCache.entities(wa));
    };
    let syncing = false;
    let queued = false;
    const syncSoon = async () => {
      if (syncing) { queued = true; return; }
      syncing = true;
      try {
        do {
          queued = false;
          await syncTiles();
        } while (queued && !dead);
      } finally {
        syncing = false;
      }
    };

    // ---- the minute poll ---------------------------------------------------------------------------------------------------
    const pollWorld = async () => {
      const [s, d] = await Promise.all([fetchSnapshot<Summary>("summary"), fetchSnapshot<DensityDoc>("density")]);
      if (dead) return;
      if (s) setSummary(s);
      if (d) {
        if (!isTiled) { isTiled = true; setTiled(true); setShips([]); setPlanes([]); }
        const v = d.layers.vessels, a = d.layers.aircraft;
        tracks.setDensity("ship", { deg: d.deg, cells: v.cells });
        tracks.setDensity("air", { deg: d.deg, cells: a.cells });
        setTotals({ ships: { n: v.n, counts: v.counts, as_of: d.as_of }, air: { n: a.n, counts: a.counts, as_of: d.aircraft_as_of ?? d.as_of } });
        await syncSoon();
        return;
      }
      // the old layout: the whole world in two documents
      if (isTiled) { isTiled = false; setTiled(false); }
      const [v, a] = await Promise.all([fetchSnapshot<VesselsDoc>("vessels"), fetchSnapshot<AircraftDoc>("aircraft")]);
      if (dead) return;
      tracks.setDensity("ship", null);
      tracks.setDensity("air", null);
      if (v) { setShips(decodeVessels(v)); }
      if (a) { setPlanes(decodeAircraft(a)); }
      setTotals((t) => ({ ships: v ? { n: v.n, counts: v.counts, as_of: v.as_of } : t.ships, air: a ? { n: a.n, counts: a.counts, as_of: a.as_of } : t.air }));
    };

    const pollSlow = async () => {
      const [f, c] = await Promise.all([fetchSnapshot<FiresDoc>("fires"), fetchSnapshot<CoverageDoc>("coverage")]);
      if (dead) return;
      if (f) setFires(f);
      if (c) setCoverage(c);
    };

    const poll = async (force = false) => {
      if (!active()) return;
      const now = Date.now();
      if (force || now - lastPoll >= POLL_MS - 2000) {
        lastPoll = now;
        await pollWorld();
      }
      if (now - lastSlow >= SLOW_MS - 2000) {
        lastSlow = now;
        await pollSlow();
      }
    };

    // ---- when to run -------------------------------------------------------------------------------------------------------
    const tick = setInterval(() => void poll(), POLL_MS);
    const onVisible = () => void poll();
    document.addEventListener("visibilitychange", onVisible);
    const io = typeof IntersectionObserver !== "undefined" && wrap.current
      ? new IntersectionObserver((es) => {
          onscreen = es.some((e) => e.isIntersecting);
          if (onscreen) void poll();
        }, { rootMargin: "150px" })
      : null;
    if (io && wrap.current) io.observe(wrap.current);
    let moved: ReturnType<typeof setTimeout> | undefined;
    const offView = tracks.addViewListener(() => {
      clearTimeout(moved);
      moved = setTimeout(() => { if (active() && isTiled) void syncSoon(); }, VIEW_DEBOUNCE_MS);
    });
    if (!io) void poll(true);
    return () => {
      dead = true;
      clearInterval(tick);
      clearTimeout(moved);
      document.removeEventListener("visibilitychange", onVisible);
      io?.disconnect();
      offView();
    };
  }, [tracks, wrap]);

  return { summary, ships, planes, totals, tiled, fires, coverage };
}
