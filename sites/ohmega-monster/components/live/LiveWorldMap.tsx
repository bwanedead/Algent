"use client";

import { useMemo, useState } from "react";

import LiveMap, { type MapStatus } from "@/components/map/LiveMap";
import { KIND_LABEL, type LiveEvent, type LiveStat, type LiveWorld } from "@/lib/live-shared";

import { eventItem, LAYERS, shipItems, type Layer } from "./liveItems";
import { GROUPS, liveLayers, WORLD_BOUNDS } from "./liveLayers";
import LiveWorldStatic from "./LiveWorldStatic";

// The /live world map: one interactive map (MapLibre over OpenFreeMap, components/map/LiveMap.tsx) with a toggleable
// layer per kind of live item. Outages are country fills, quakes sized circles, military aircraft clusters, fires heat,
// chokepoint counting lines carry today's count. Every item is ALSO a row in the list under the map (a tap target that
// works on a phone, and the accessible route); selecting a mark or a row opens the same plain-language detail card.
// While the map loads, without JS or WebGL, or if the CDN fails, the SVG map (LiveWorldStatic) shows instead.

const BASEMAP_CREDIT = "Interactive basemap: OpenFreeMap, © OpenMapTiles, data © OpenStreetMap contributors.";

export default function LiveWorldMap({ world, events, stats }: { world: LiveWorld | null; events: LiveEvent[]; stats: LiveStat[] }) {
  const items = useMemo(() => [...events.filter((e) => e.ends_at === null || e.kind !== "outage").map(eventItem), ...shipItems(stats)], [events, stats]);
  const [off, setOff] = useState<Set<Layer>>(new Set());
  const [sel, setSel] = useState<string | null>(null);
  const [status, setStatus] = useState<MapStatus>("loading");
  const counts = useMemo(() => {
    const c: Partial<Record<Layer, number>> = {};
    for (const i of items) c[i.layer] = (c[i.layer] ?? 0) + 1;
    return c;
  }, [items]);
  const shown = items.filter((i) => !off.has(i.layer));
  const current = items.find((i) => i.id === sel) ?? null;
  const layers = useMemo(() => liveLayers(items, world), [items, world]);
  const hidden = useMemo(() => Array.from(off).flatMap((l) => GROUPS[l]), [off]);
  const toggle = (l: Layer) =>
    setOff((cur) => {
      const n = new Set(cur);
      if (n.has(l)) n.delete(l);
      else n.add(l);
      return n;
    });

  return (
    <div className="live-map-wrap">
      <div className="live-layers" role="group" aria-label="Map layers">
        {LAYERS.map((l) => (
          <button key={l.id} type="button" className={`live-layer${off.has(l.id) ? "" : " is-on"}`} aria-pressed={!off.has(l.id)} onClick={() => toggle(l.id)}>
            <span aria-hidden="true" className={`live-glyph live-glyph-${l.id}`}>{l.glyph}</span> {l.label} <span className="live-count">{counts[l.id] ?? 0}</span>
          </button>
        ))}
      </div>

      {world ? (
        <div className="live-map-int">
          <LiveMap
            layers={layers}
            bounds={WORLD_BOUNDS}
            label={`World map with ${shown.length} live items. The same items are listed below the map.`}
            aspect={1.7}
            maxZoom={4}
            hidden={hidden}
            selectedId={sel}
            onSelect={(id) => setSel(id)}
            onStatus={setStatus}
            fallback={<LiveWorldStatic world={world} items={shown} sel={sel} onSelect={setSel} bare />}
            credit={status === "failed" ? world.credit : `${world.credit} ${BASEMAP_CREDIT}`}
          />
        </div>
      ) : (
        <p className="live-empty">The world map is not published yet. The items are listed below.</p>
      )}

      {current && (
        <section className="live-card" aria-label="Item detail">
          <button type="button" className="live-card-x" aria-label="Close detail" onClick={() => setSel(null)}>×</button>
          <p className="live-card-kind">{current.layer === "ships" ? "Ship traffic" : KIND_LABEL[current.layer]}{current.major ? " · major" : ""}</p>
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

      <ul className="live-list" aria-label="All live items">
        {shown.length === 0 && <li className="live-empty">Nothing in the selected layers right now.</li>}
        {shown.map((it) => (
          <li key={it.id}>
            <button type="button" className={`live-row${sel === it.id ? " is-on" : ""}`} onClick={() => setSel(it.id)}>
              <span aria-hidden="true" className={`live-glyph live-glyph-${it.layer}`}>{LAYERS.find((l) => l.id === it.layer)?.glyph}</span>
              <span className="live-row-title">{it.title}</span>
              {it.when && <span className="live-row-when">{it.when}</span>}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
