"use client";

import { useMemo, useState } from "react";

import { KIND_LABEL, whenUtc, type LiveEvent, type LiveKind, type LiveStat, type LiveWorld } from "@/lib/live-shared";

// The /live world map: the desk's Natural Earth countries (published by the backend as `live/world.json`) with one
// mark per live item, each layer toggleable. The map is a light "printed" panel in both themes (map-local colours in
// live.css, like the daily's maps). Marks are small, so every item is ALSO a row in the list under the map: a tap target
// that works on a phone, and the accessible route. Selecting either opens the same plain-language detail card.

type Item = { id: string; layer: Layer; title: string; detail: string; when: string; source: string; url: string; lat: number | null; lon: number | null; size: number; major: boolean };
type Layer = LiveKind | "ships";

const LAYERS: { id: Layer; label: string; glyph: string }[] = [
  { id: "outage", label: "Internet outages", glyph: "■" },
  { id: "quake", label: "Earthquakes", glyph: "●" },
  { id: "aircraft", label: "Military aircraft", glyph: "▲" },
  { id: "fire", label: "Fire hotspots", glyph: "◆" },
  { id: "ships", label: "Ship traffic", glyph: "◎" },
];

const safeUrl = (u: string) => (/^https?:\/\//.test(u) ? u : "");

function eventItem(e: LiveEvent): Item {
  const mag = typeof e.data.magnitude === "number" ? e.data.magnitude : 0;
  const count = typeof e.data.count === "number" ? e.data.count : typeof e.data.hotspots === "number" ? e.data.hotspots : 1;
  return {
    id: e.id,
    layer: e.kind,
    title: e.title,
    detail: e.detail,
    when: e.ends_at ? `${whenUtc(e.starts_at)} to ${whenUtc(e.ends_at)}` : e.starts_at ? `since ${whenUtc(e.starts_at)}` : "",
    source: e.source,
    url: safeUrl(e.source_url),
    lat: e.lat,
    lon: e.lon,
    size: e.kind === "quake" ? Math.max(1, mag - 3.5) : Math.min(3, 1 + Math.log2(count)),
    major: e.severity === "major",
  };
}

function shipItems(stats: LiveStat[]): Item[] {
  const last = new Map<string, LiveStat>();
  for (const s of stats) if (s.kind === "ships" && !s.partial) last.set(s.region, s);
  return Array.from(last.values()).map((s) => ({
    id: s.series_id,
    layer: "ships" as const,
    title: `${s.name.split(" — ")[0]}: ${s.value} ships crossed on ${s.period}`,
    detail: "Ships whose tracking signal crossed our counting line in this strait that day, counted by Ohmega from live ship-position broadcasts. Ships with their transponder off are not seen, so read it against its own recent days, not as a total.",
    when: `day ending ${s.period} 24:00 UTC`,
    source: "Ohmega count from aisstream.io",
    url: safeUrl(s.source_url),
    lat: s.lat,
    lon: s.lon,
    size: 1.4,
    major: false,
  }));
}

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
    case "ships":
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

export default function LiveMap({ world, events, stats }: { world: LiveWorld | null; events: LiveEvent[]; stats: LiveStat[] }) {
  const items = useMemo(() => [...events.filter((e) => e.ends_at === null || e.kind !== "outage").map(eventItem), ...shipItems(stats)], [events, stats]);
  const [off, setOff] = useState<Set<Layer>>(new Set());
  const [sel, setSel] = useState<string | null>(null);
  const counts = useMemo(() => {
    const c: Partial<Record<Layer, number>> = {};
    for (const i of items) c[i.layer] = (c[i.layer] ?? 0) + 1;
    return c;
  }, [items]);
  const shown = items.filter((i) => !off.has(i.layer));
  const current = items.find((i) => i.id === sel) ?? null;
  const toggle = (l: Layer) =>
    setOff((cur) => {
      const n = new Set(cur);
      if (n.has(l)) n.delete(l);
      else n.add(l);
      return n;
    });

  const project = (lat: number, lon: number): [number, number] | null => {
    if (!world) return null;
    const [w, s, e, n] = world.bbox;
    if (lon < w || lon > e || lat < s || lat > n) return null;
    return [((lon - w) / (e - w)) * world.width, ((n - lat) / (n - s)) * world.height];
  };

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
        <figure className="live-map">
          <svg viewBox={`0 0 ${world.width} ${world.height}`} role="img" className="live-map-svg" aria-label={`World map with ${shown.length} live items. The same items are listed below the map.`}>
            <rect width={world.width} height={world.height} className="live-map-sea" />
            {world.countries.map((c, i) => (
              <path key={i} d={c.d} className="live-map-land">
                <title>{c.name}</title>
              </path>
            ))}
            {shown.map((it) => {
              const p = it.lat !== null && it.lon !== null ? project(it.lat, it.lon) : null;
              if (!p) return null;
              return (
                <g key={it.id} className="live-hit" role="button" tabIndex={0} aria-label={it.title} onClick={() => setSel(it.id)}
                   onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSel(it.id); } }}>
                  <circle cx={p[0]} cy={p[1]} r={26} className="live-hit-area" />
                  <Mark it={it} x={p[0]} y={p[1]} on={sel === it.id} />
                </g>
              );
            })}
          </svg>
          <figcaption className="live-credit">{world.credit}</figcaption>
        </figure>
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
