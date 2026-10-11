"use client";

import type { LiveWorld } from "@/lib/live-shared";

import type { Item } from "./liveItems";

// The /live map as plain SVG: the fallback behind the interactive map (while it loads, with no JS or WebGL, or when the
// CDN is down). Countries come from the backend's `live/world.json`; one mark per item, differing by SHAPE as well as
// colour. Selecting a mark opens the same detail card as the interactive map. Colours: app/live/live.css (map-local).

function Mark({ it, x, y, on }: { it: Item; x: number; y: number; on: boolean }) {
  const r = 5 + it.size * 2.2;
  const cls = `live-mark live-mark-${it.layer}${it.major ? " is-major" : ""}${on ? " is-on" : ""}`;
  switch (it.layer) {
    case "outage":
      return <rect className={cls} x={x - r} y={y - r} width={r * 2} height={r * 2} />;
    case "aircraft":
      return <path className={cls} d={`M${x} ${y - r * 1.2}L${x + r * 1.1} ${y + r * 0.8}L${x - r * 1.1} ${y + r * 0.8}Z`} />;
    case "fire":
      return <path className={cls} d={`M${x} ${y - r}L${x + r} ${y}L${x} ${y + r}L${x - r} ${y}Z`} />;
    case "gates":
      return (
        <g className={cls}>
          <circle cx={x} cy={y} r={r} />
          <circle cx={x} cy={y} r={r * 0.35} className="live-mark-core" />
        </g>
      );
    default:
      return <circle className={cls} cx={x} cy={y} r={r} />;
  }
}

export default function LiveWorldStatic({ world, items, sel, onSelect, bare = false }: { world: LiveWorld; items: Item[]; sel: string | null; onSelect: (id: string) => void; bare?: boolean }) {
  const project = (lat: number, lon: number): [number, number] | null => {
    const [w, s, e, n] = world.bbox;
    if (lon < w || lon > e || lat < s || lat > n) return null;
    return [((lon - w) / (e - w)) * world.width, ((n - lat) / (n - s)) * world.height];
  };
  return (
    <figure className="live-map">
      <svg viewBox={`0 0 ${world.width} ${world.height}`} role="img" className="live-map-svg" aria-label={`World map with ${items.length} live items. The same items are listed below the map.`}>
        <rect width={world.width} height={world.height} className="live-map-sea" />
        {world.countries.map((c, i) => (
          <path key={i} d={c.d} className="live-map-land">
            <title>{c.name}</title>
          </path>
        ))}
        {items.map((it) => {
          const p = it.lat !== null && it.lon !== null ? project(it.lat, it.lon) : null;
          if (!p) return null;
          return (
            <g key={it.id} className="live-hit" role="button" tabIndex={0} aria-label={it.title} onClick={() => onSelect(it.id)}
               onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(it.id); } }}>
              <circle cx={p[0]} cy={p[1]} r={26} className="live-hit-area" />
              <Mark it={it} x={p[0]} y={p[1]} on={sel === it.id} />
            </g>
          );
        })}
      </svg>
      {!bare && <figcaption className="live-credit">{world.credit}</figcaption>}
    </figure>
  );
}
