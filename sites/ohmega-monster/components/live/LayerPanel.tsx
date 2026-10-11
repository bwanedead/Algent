"use client";

import { useState } from "react";

import type { Entity } from "./entities";

// The layer panel: layers and sublayers as toggle chips that double as the legend (colour dot, count, freshness), then the
// filters for the moving layers (speed, notable, flag state, search by name / MMSI / callsign) and the trails switch.
// State lives in the parent (LiveWorldMap), which persists the toggles.

export type PanelRow = { key: string; label: string; color: string; count: number | null; fresh: string; subs?: PanelRow[] };
export type FilterState = { speed: "all" | "moving" | "stopped"; notable: boolean; flag: string; q: string };

type Props = {
  rows: PanelRow[];
  off: Set<string>;
  onToggle: (key: string) => void;
  filters: FilterState;
  onFilters: (patch: Partial<FilterState>) => void;
  flags: { code: string; label: string; n: number }[];
  results: Entity[];
  onPick: (e: Entity) => void;
  trails: boolean;
  onTrails: (on: boolean) => void;
  shown: string;
};

function Chip({ row, off, parentOff, onToggle, sub = false }: { row: PanelRow; off: Set<string>; parentOff?: boolean; onToggle: (k: string) => void; sub?: boolean }) {
  const on = !off.has(row.key) && !parentOff;
  return (
    <button type="button" className={`live-chip${on ? " is-on" : ""}${sub ? " is-sub" : ""}`} aria-pressed={on} onClick={() => onToggle(row.key)} disabled={parentOff}>
      <span className="live-chip-dot" style={{ background: row.color }} aria-hidden="true" />
      <span className="live-chip-label">{row.label}</span>
      {row.count !== null && <span className="live-count">{row.count.toLocaleString("en-GB")}</span>}
      {row.fresh && <span className="live-fresh">{row.fresh}</span>}
    </button>
  );
}

export default function LayerPanel({ rows, off, onToggle, filters, onFilters, flags, results, onPick, trails, onTrails, shown }: Props) {
  const [more, setMore] = useState(false);
  return (
    <div className="live-panel">
      <div className="live-layers" role="group" aria-label="Map layers">
        {rows.map((r) => (
          <div key={r.key} className="live-layer-group">
            <Chip row={r} off={off} onToggle={onToggle} />
            {r.subs && (
              <div className="live-subs" role="group" aria-label={`${r.label} types`}>
                {r.subs.map((s) => <Chip key={s.key} row={s} off={off} parentOff={off.has(r.key)} onToggle={onToggle} sub />)}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="live-filters" role="group" aria-label="Ship and aircraft filters">
        <div className="live-seg" role="group" aria-label="Movement">
          {(["all", "moving", "stopped"] as const).map((v) => (
            <button key={v} type="button" className={filters.speed === v ? "is-on" : ""} aria-pressed={filters.speed === v} onClick={() => onFilters({ speed: v })}>
              {v === "all" ? "All" : v === "moving" ? "Underway" : "Stopped"}
            </button>
          ))}
        </div>
        <button type="button" className={`live-toggle${filters.notable ? " is-on" : ""}`} aria-pressed={filters.notable} onClick={() => onFilters({ notable: !filters.notable })}>
          Notable only
        </button>
        <button type="button" className={`live-toggle${trails ? " is-on" : ""}`} aria-pressed={trails} onClick={() => onTrails(!trails)}>
          Trails for visible
        </button>
        <button type="button" className="live-toggle" aria-expanded={more} onClick={() => setMore(!more)}>
          {more ? "Fewer filters" : "Flag and search"}
        </button>
      </div>

      {more && (
        <div className="live-filters-more">
          <label className="live-field">
            <span>Flag state</span>
            <select value={filters.flag} onChange={(e) => onFilters({ flag: e.target.value })}>
              <option value="">All flags</option>
              {flags.map((f) => <option key={f.code} value={f.code}>{f.label} ({f.n})</option>)}
            </select>
          </label>
          <label className="live-field">
            <span>Search name, MMSI or callsign</span>
            <input type="search" value={filters.q} placeholder="e.g. NORD or 636" onChange={(e) => onFilters({ q: e.target.value })} />
          </label>
        </div>
      )}

      {filters.q.length >= 2 && results.length > 0 && (
        <ul className="live-results" aria-label="Search results">
          {results.map((e) => (
            <li key={`${e.kind}:${e.id}`}>
              <button type="button" onClick={() => onPick(e)}>{e.name || (e.kind === "ship" ? `Vessel ${e.id}` : "Aircraft")} <span className="live-muted">{e.kind === "ship" ? `MMSI ${e.id}` : e.type}</span></button>
            </li>
          ))}
        </ul>
      )}
      {shown && <p className="live-note live-shown">{shown}</p>}
    </div>
  );
}
