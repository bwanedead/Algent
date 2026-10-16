"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Bounds, LngLat } from "@/components/map/geo";
import LiveMap, { type MapStatus } from "@/components/map/LiveMap";
import {
  ago, ANOMALY_COLOR, compact, fetchSnapshot, KIND_LABEL, shipTiles, strongest,
  type CoverageDoc, type FiresDoc, type Headline, type LiveAnomaly, type LiveEvent, type LiveStat, type LiveWorld, type Summary,
} from "@/lib/live-shared";

import ChokepointTiles from "./ChokepointTiles";
import { AIR_KINDS, NO_FILTER, passes, regionName, SHIP_CLASSES, type Entity } from "./entities";
import Headlines from "./Headlines";
import LayerPanel, { type FilterState, type PanelRow } from "./LayerPanel";
import { eventItem, gateItems } from "./liveItems";
import { anomalyRings, COLOR, GROUPS, liveLayers, WORLD_BOUNDS } from "./liveLayers";
import LiveWorldStatic from "./LiveWorldStatic";
import { Tracks } from "./TrackLayers";
import UnusualStrip from "./UnusualStrip";
import { loadTrails, type Trail } from "./trails";
import { useLiveEntities } from "./useLiveEntities";

// The /live world map and everything around it. One interactive map (MapLibre over OpenFreeMap, components/map/LiveMap.tsx):
//   - events (outage fills, quakes, fire heat, chokepoint lines) are declarative layers (liveLayers.ts);
//   - ships and aircraft are the moving layers (TrackLayers.ts): density far out, dots, then heading-oriented icons dead-reckoned
//     between the once-a-minute snapshots, with filters, search and short trails (entities.ts, trails.ts).
// Data is polled from the public Storage bucket (lib/live-shared.ts `fetchSnapshot`; the big documents arrive gzipped): the summary
// every minute, fire heat and the AIS receiver-coverage grid every ten; ships and aircraft by view (useLiveEntities.ts: compact
// points far out, tiles under the viewport zoomed in, the full snapshots when a filter needs them). The layer toggles persist in
// localStorage; receiver coverage starts off. While the map loads, without JS or WebGL, or if the CDN
// fails, the SVG map (LiveWorldStatic) shows the events instead.

const BASEMAP_CREDIT = "Interactive basemap: OpenFreeMap, © OpenMapTiles, data © OpenStreetMap contributors.";
const DATA_CREDIT = "Ships: aisstream.io, Fintraffic digitraffic.fi (CC 4.0 BY), Norwegian Coastal Administration (NLOD). Aircraft: OpenSky Network, adsb.lol. Fires: NASA FIRMS. Quakes: USGS. Outages: IODA.";
const STORE_KEY = "ohmega-live-off-v2"; // v2: coverage became off by default
const POLL_MS = 60_000;
const FIRES_MS = 600_000;
const REFRESH_TRAILS_MS = 300_000;

const pull = fetchSnapshot;

const reduceMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const HEADLINE_TOGGLE: Record<Headline["layer"], string> = { outage: "outage", quake: "quake", fire: "fire", ships: "ships", aircraft: "aircraft" };

type Focus = { nonce: number; bounds?: Bounds; center?: LngLat; zoom?: number };

export default function LiveWorldMap({ world, events, stats, summary: summary0, anomalies }: { world: LiveWorld | null; events: LiveEvent[]; stats: LiveStat[]; summary: Summary | null; anomalies: LiveAnomaly[] }) {
  const [summary, setSummary] = useState<Summary | null>(summary0);
  const [fires, setFires] = useState<FiresDoc | null>(null);
  const [coverage, setCoverage] = useState<CoverageDoc | null>(null);
  const [off, setOff] = useState<Set<string>>(new Set(["coverage"]));
  const [filters, setFilters] = useState<FilterState>({ speed: "all", notable: false, flag: "", q: "" });
  const [sel, setSel] = useState<string | null>(null);
  const [selEnt, setSelEnt] = useState<Entity | null>(null);
  const [status, setStatus] = useState<MapStatus>("loading");
  const [focus, setFocus] = useState<Focus | null>(null);
  const [gate, setGate] = useState<string | null>(null);
  const [trailsOn, setTrailsOn] = useState(false);
  const [selTrail, setSelTrail] = useState<Trail[]>([]);
  const [visTrail, setVisTrail] = useState<Trail[]>([]);
  const [now, setNow] = useState<number | null>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const nonce = useRef(0);
  const tracks = useMemo(() => new Tracks((e) => setSelEnt(e)), []);

  // ---- clock, persisted toggles, polling ---------------------------------------------------------------------------
  useEffect(() => {
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      if (raw) setOff(new Set((JSON.parse(raw) as unknown[]).filter((k): k is string => typeof k === "string")));
    } catch {
      /* private mode or blocked storage: the defaults stand */
    }
  }, []);

  useEffect(() => {
    let dead = false;
    const fast = async () => {
      if (document.hidden) return;
      const s = await pull<Summary>("summary");
      if (!dead && s) setSummary(s);
    };
    const slow = async () => {
      const [f, c] = await Promise.all([pull<FiresDoc>("fires"), pull<CoverageDoc>("coverage")]);
      if (dead) return;
      if (f) setFires(f);
      if (c) setCoverage(c);
    };
    const visible = () => { if (!document.hidden) void fast(); };
    void fast();
    void slow();
    const i1 = setInterval(fast, POLL_MS);
    const i2 = setInterval(slow, FIRES_MS);
    document.addEventListener("visibilitychange", visible);
    return () => {
      dead = true;
      clearInterval(i1);
      clearInterval(i2);
      document.removeEventListener("visibilitychange", visible);
    };
  }, []);

  // ---- moving layers: entities, filters ----------------------------------------------------------------------------
  const needFull = filters.flag !== "" || filters.q !== "" || filters.speed !== "all" || filters.notable; // fields only the full rows carry
  const { ships, planes, meta, topFlags, mode } = useLiveEntities(tracks, needFull, { ships: !off.has("ships"), air: !off.has("aircraft") });
  const vessels = meta.vessels;
  const aircraft = meta.aircraft;
  useEffect(() => tracks.setEntities("ship", ships), [tracks, ships]);
  useEffect(() => tracks.setEntities("air", planes), [tracks, planes]);
  const entityFilter = useMemo(
    () => ({ ...NO_FILTER, off: new Set(Array.from(off).filter((k) => k.includes(".")).map((k) => k.split(".")[1])), flag: filters.flag, speed: filters.speed, notable: filters.notable, q: filters.q }),
    [off, filters],
  );
  useEffect(() => tracks.setFilter(entityFilter, { ship: !off.has("ships"), air: !off.has("aircraft") }), [tracks, entityFilter, off]);
  useEffect(() => tracks.setCoverage(coverage), [tracks, coverage]);
  useEffect(() => tracks.setCoverageVisible(!off.has("coverage")), [tracks, off]);
  const onMap = useCallback((map: unknown) => (map ? tracks.attach(map) : tracks.detach()), [tracks]);

  // ---- trails: the selected object's, and "visible" ones (switch or chokepoint focus) ------------------------------------
  useEffect(() => {
    if (!selEnt) { setSelTrail([]); return; }
    let dead = false;
    void loadTrails([selEnt], (e) => tracks.position(e)).then((t) => { if (!dead) setSelTrail(t); });
    return () => { dead = true; };
  }, [selEnt, tracks]);

  const wantVisible = trailsOn || gate !== null;
  useEffect(() => {
    if (!wantVisible) { setVisTrail([]); return; }
    let dead = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const run = async () => {
      const t = await loadTrails(tracks.visibleEntities(), (e) => tracks.position(e));
      if (!dead) setVisTrail(t);
    };
    tracks.onView = () => { clearTimeout(timer); timer = setTimeout(() => void run(), 600); };
    void run();
    const again = setInterval(() => void run(), REFRESH_TRAILS_MS);
    return () => { dead = true; clearTimeout(timer); clearInterval(again); tracks.onView = null; };
  }, [wantVisible, tracks, ships, planes]);
  useEffect(() => tracks.setTrails([...visTrail, ...selTrail]), [tracks, visTrail, selTrail]);

  // ---- events and declarative layers --------------------------------------------------------------------------------
  const gates = summary?.gates;
  const gatesKey = JSON.stringify(Object.entries(gates ?? {}).map(([k, g]) => [k, g.in_strait ?? null]));
  const stableGates = useMemo(() => gates, [gatesKey]); // eslint-disable-line react-hooks/exhaustive-deps -- relabel only when a count changes
  const items = useMemo(() => [...events.filter((e) => e.ends_at === null || e.kind !== "outage").map(eventItem), ...gateItems(stableGates)], [events, stableGates]);
  const rings = useMemo(() => anomalyRings(anomalies), [anomalies]);
  const layers = useMemo(() => [...liveLayers(items, world, fires, stableGates), ...(rings ? [rings] : [])], [items, world, fires, stableGates, rings]);
  const hidden = useMemo(() => Array.from(off).filter((k) => !k.includes(".")).flatMap((l) => GROUPS[l as keyof typeof GROUPS] ?? []), [off]);
  const unusual = useMemo(() => strongest(anomalies), [anomalies]);
  const nUnusual = anomalies.filter((a) => a.active).length;
  const shownItems = items.filter((i) => !off.has(i.layer));
  const current = items.find((i) => i.id === sel) ?? null;

  // ---- the panel ----------------------------------------------------------------------------------------------------
  const when = (iso: string | undefined) => (now !== null && iso ? ago(iso, now) : "");
  const nOutages = events.filter((e) => e.kind === "outage" && e.ends_at === null).length;
  const nQuakes = events.filter((e) => e.kind === "quake").length;
  const rows: PanelRow[] = [
    { key: "ships", label: "Ships", color: "#3fb0a8", count: vessels ? vessels.n : null, fresh: when(vessels?.as_of ?? summary?.fresh.ships),
      subs: SHIP_CLASSES.map((c) => ({ key: `ships.${c.key}`, label: c.key === "military" ? "Military / police" : c.label, color: c.color, count: vessels?.counts?.[c.key] ?? null, fresh: "" })) },
    { key: "aircraft", label: "Aircraft", color: "#8b6fd6", count: aircraft ? aircraft.n : null, fresh: when(aircraft?.as_of ?? summary?.fresh.aircraft),
      subs: AIR_KINDS.map((k) => ({ key: `aircraft.${k.key}`, label: k.label, color: k.color, count: aircraft?.counts?.[k.key] ?? null, fresh: "" })) },
    { key: "coverage", label: "AIS receiver coverage", color: "#3fb0a8", count: null, fresh: coverage ? "last 24 h" : "" },
    { key: "fire", label: KIND_LABEL.fire, color: COLOR.fire, count: fires?.detections ?? summary?.fires?.detections ?? null, fresh: when(fires?.as_of ?? summary?.fresh.fire) },
    { key: "quake", label: KIND_LABEL.quake, color: COLOR.quake, count: nQuakes, fresh: when(summary?.fresh.quake) },
    { key: "outage", label: KIND_LABEL.outage, color: COLOR.outage, count: nOutages, fresh: when(summary?.fresh.outage) },
    { key: "gates", label: "Chokepoints", color: COLOR.gates, count: Object.keys(gates ?? {}).length, fresh: "" },
    ...(anomalies.length > 0 ? [{ key: "anomalies", label: "Anomalies", color: ANOMALY_COLOR.above, count: nUnusual, fresh: "" }] : []),
  ];
  const flags = useMemo(() => {
    if (mode !== "full") return topFlags.map(([code, c]) => ({ code, label: regionName(code), n: c }));
    const n = new Map<string, number>();
    for (const s of ships) if (s.flag) n.set(s.flag, (n.get(s.flag) ?? 0) + 1);
    return Array.from(n.entries()).sort((a, b) => b[1] - a[1]).slice(0, 40).map(([code, c]) => ({ code, label: regionName(code), n: c }));
  }, [ships, mode, topFlags]);
  const results = useMemo(() => {
    if (filters.q.length < 2) return [];
    const only = { ...NO_FILTER, q: filters.q };
    return [...ships, ...planes].filter((e) => passes(e, only)).slice(0, 8);
  }, [ships, planes, filters.q]);
  const shownText = useMemo(() => {
    const s = off.has("ships") ? 0 : ships.filter((e) => passes(e, entityFilter)).length;
    const a = off.has("aircraft") ? 0 : planes.filter((e) => passes(e, entityFilter)).length;
    const nShips = vessels?.n ?? ships.length;
    const nAir = aircraft?.n ?? planes.length;
    const shown = mode === "tiles" ? `Showing ${compact(s)} ships and ${compact(a)} aircraft in this view (${compact(nShips)} and ${compact(nAir)} worldwide)` : `Showing ${compact(s)} of ${compact(nShips)} ships and ${compact(a)} of ${compact(nAir)} aircraft`;
    return ships.length + planes.length === 0 ? "" : `${shown}. Zoom in past a region for individual icons; far out you see density. Ships are seen only within reach of AIS receivers (switch on AIS receiver coverage to see where): empty ocean may mean no receiver, not no ships.`;
  }, [ships, planes, entityFilter, off, mode, vessels, aircraft]);

  const toggle = (key: string) => {
    const n = new Set(off);
    if (n.has(key)) n.delete(key);
    else n.add(key);
    setOff(n);
    try { localStorage.setItem(STORE_KEY, JSON.stringify(Array.from(n))); } catch { /* storage blocked: the toggle still works for this visit */ }
  };

  // ---- navigation: headlines, chokepoint focus, search --------------------------------------------------------------
  const toMap = () => wrap.current?.querySelector(".live-map-int")?.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "center" });
  const focusGate = (slug: string | null) => {
    setGate(slug);
    const g = slug ? summary?.gates?.[slug] : undefined;
    if (!g?.box) return;
    setFocus({ nonce: ++nonce.current, bounds: [g.box[1], g.box[0], g.box[3], g.box[2]] });
    toMap();
  };
  const pick = (h: Headline) => {
    if (h.id.startsWith("gate:")) return focusGate(h.id.slice(5));
    if (h.lat === null || h.lon === null) return;
    const key = HEADLINE_TOGGLE[h.layer];
    if (off.has(key)) toggle(key);
    setGate(null);
    setFocus({ nonce: ++nonce.current, center: [h.lon, h.lat], zoom: h.zoom });
    if (items.some((i) => i.id === h.id)) setSel(h.id);
    toMap();
  };
  const pickAnomaly = (a: LiveAnomaly) => {
    if (a.lat === null || a.lon === null) return;
    if (off.has("anomalies")) toggle("anomalies");
    setGate(null);
    setFocus({ nonce: ++nonce.current, center: [a.lon, a.lat], zoom: a.place_kind === "cell" ? 6 : 5 });
    toMap();
  };
  const pickEntity = (e: Entity) => {
    setFocus({ nonce: ++nonce.current, center: tracks.position(e), zoom: 9 });
    tracks.select(e);
    toMap();
  };

  const gateNow = gate ? summary?.gates?.[gate] : undefined;
  const gateTile = shipTiles(stats);

  return (
    <div className="live-map-wrap" ref={wrap}>
      <Headlines items={summary?.headlines ?? []} asOf={summary?.as_of ?? ""} now={now} onPick={pick} />

      <UnusualStrip rows={unusual} onPick={pickAnomaly} />

      <LayerPanel
        rows={rows} off={off} onToggle={toggle}
        filters={filters} onFilters={(p) => setFilters((f) => ({ ...f, ...p }))}
        flags={flags} results={results} onPick={pickEntity}
        trails={trailsOn} onTrails={setTrailsOn} shown={shownText}
      />

      {gateNow && (
        <p className="live-focusbar" role="status">
          Focused on <strong>{gateNow.label}</strong>: {typeof gateNow.in_strait === "number" ? `${gateNow.in_strait} ships in the strait now. ` : ""}Icons point the way each ship is heading; lines are the last two hours.
          <button type="button" className="live-linkbtn" onClick={() => focusGate(null)}>Exit focus</button>
        </p>
      )}

      {world ? (
        <div className="live-map-int">
          <LiveMap
            layers={layers}
            bounds={WORLD_BOUNDS}
            label="World map of live ships, aircraft, fires, earthquakes and internet outages. The events are also listed below the map."
            aspect={1.7}
            maxZoom={4}
            hidden={hidden}
            selectedId={sel}
            onSelect={(id) => setSel(id)}
            onStatus={setStatus}
            onMap={onMap}
            focus={focus}
            fallback={<LiveWorldStatic world={world} items={shownItems} sel={sel} onSelect={setSel} bare />}
            credit={status === "failed" ? world.credit : `${world.credit} ${BASEMAP_CREDIT} ${DATA_CREDIT}`}
          />
        </div>
      ) : (
        <p className="live-empty">The world map is not published yet. The events are listed below.</p>
      )}

      {current && (
        <section className="live-card" aria-label="Item detail">
          <button type="button" className="live-card-x" aria-label="Close detail" onClick={() => setSel(null)}>×</button>
          <p className="live-card-kind">{current.layer === "gates" ? "Chokepoint" : KIND_LABEL[current.layer]}{current.major ? " · major" : ""}</p>
          <h3 className="live-card-title">{current.title}</h3>
          {current.when && <p className="live-card-when">{current.when}</p>}
          <p className="live-card-text">{current.detail}</p>
          {current.url ? (
            <p className="live-card-src">Source: <a className="xt" href={current.url} target="_blank" rel="noopener noreferrer">{current.source || "open source"} ↗</a></p>
          ) : (
            <p className="live-card-src">Source: {current.source}</p>
          )}
        </section>
      )}

      <section aria-labelledby="live-choke">
        <h2 id="live-choke" className="live-h2">Chokepoints</h2>
        <ChokepointTiles tiles={gateTile} gates={summary?.gates ?? {}} focus={gate} onFocus={focusGate} fresh={when(vessels?.as_of ?? summary?.fresh.ships)} />
      </section>

      <details className="live-events">
        <summary>All events ({shownItems.length})</summary>
        <ul className="live-list" aria-label="All live events">
          {shownItems.length === 0 && <li className="live-empty">Nothing in the selected layers right now.</li>}
          {shownItems.map((it) => (
            <li key={it.id}>
              <button type="button" className={`live-row${sel === it.id ? " is-on" : ""}`} onClick={() => setSel(it.id)}>
                <span aria-hidden="true" className="live-chip-dot" style={{ background: it.layer === "gates" ? COLOR.gates : it.layer === "aircraft" ? "#8b6fd6" : COLOR[it.layer] }} />
                <span className="live-row-title">{it.title}</span>
                {it.when && <span className="live-row-when">{it.when}</span>}
              </button>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
