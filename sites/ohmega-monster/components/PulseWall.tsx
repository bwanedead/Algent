"use client";

// The /pulses scanner: a dense wall of uniform PulseTiles, sortable. Detail opens in the shared
// Popover (deep links #pulse-<id> are handled there). Sort/period live in the URL (?sort=&period=) so
// a view can be shared. Pure ordering/layout maths is in lib/pulse-wall.ts; this file owns state and layout.

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import {
  DEFAULT_PERIOD,
  DEFAULT_SORT,
  PERIODS,
  SORTS,
  SORT_LABEL,
  parsePeriod,
  parseSort,
  periodChange,
  sortItems,
  spiralCells,
  type Period,
  type SortKey,
  type WallPulse,
} from "@/lib/pulse-wall";

import PulseTile from "./PulseTile";

const GAP = 6;
const MIN_TILE = 150;
const MIN_TILE_PHONE = 104;
const SPIRAL_MIN_COLS = 4; // narrower than this the spiral has no centre worth speaking of: plain list order

/** Columns an auto-fill grid of this width produces (mirrors the CSS minmax(min, 1fr) track). */
function columnsFor(width: number): number {
  const phone = typeof window !== "undefined" && window.matchMedia("(max-width: 640px)").matches;
  const min = phone ? MIN_TILE_PHONE : MIN_TILE;
  return Math.max(1, Math.floor((width + GAP) / (min + GAP)));
}

function asOfMs(asOf: string, pulses: WallPulse[]): number {
  const t = Date.parse(asOf);
  if (Number.isFinite(t)) return t;
  let best = -Infinity;
  for (const p of pulses) for (const h of p.history) best = Math.max(best, Date.parse(h.at) || -Infinity);
  return best;
}

export default function PulseWall({ pulses, asOf, asOfLabel }: { pulses: WallPulse[]; asOf: string; asOfLabel: string }) {
  const [sort, setSort] = useState<SortKey>(DEFAULT_SORT);
  const [period, setPeriod] = useState<Period>(DEFAULT_PERIOD);
  const [cols, setCols] = useState(0);
  const gridRef = useRef<HTMLDivElement>(null);

  // ---- URL <-> state ----------------------------------------------------------------------
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setSort(parseSort(q.get("sort")));
    setPeriod(parsePeriod(q.get("period")));
  }, []);

  const writeUrl = useCallback((s: SortKey, per: Period) => {
    const q = new URLSearchParams();
    if (s !== DEFAULT_SORT) q.set("sort", s);
    if (per !== DEFAULT_PERIOD) q.set("period", per);
    const qs = q.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${qs ? `?${qs}` : ""}${window.location.hash}`);
  }, []);
  const chooseSort = (s: SortKey) => {
    setSort(s);
    writeUrl(s, period);
  };
  const choosePeriod = (per: Period) => {
    setPeriod(per);
    writeUrl(sort, per);
  };

  // ---- ordering ---------------------------------------------------------------------------
  const ref = useMemo(() => asOfMs(asOf, pulses), [asOf, pulses]);
  const items = useMemo(() => sortItems(pulses.map((p) => ({ p, ...periodChange(p, period, ref) })), sort), [pulses, period, sort, ref]);
  const showMoves = sort === "moves" || sort === "spiral";

  // ---- spiral: measured column count, deterministic cell placement ---------------------------
  useEffect(() => {
    const el = gridRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const measure = () => setCols(columnsFor(el.clientWidth));
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [pulses.length]);
  const spiral = sort === "spiral" && cols >= SPIRAL_MIN_COLS;
  const cells = useMemo(() => (spiral ? spiralCells(items.length, cols) : []), [spiral, items.length, cols]);
  const gridStyle: CSSProperties | undefined = spiral ? { gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` } : undefined;

  const assessed = pulses.filter((p) => p.position !== null).length;

  return (
    <>
      <div className="intel-strip wall-strip" role="group" aria-label="Pulses controls">
        <span className="intel-strip-title">Pulses</span>
        <span className="intel-strip-item">
          <span className="intel-micro">As of</span> {asOfLabel}
        </span>
        <span className="intel-strip-item">
          <b className="intel-num-sm">{pulses.length}</b> <span className="intel-micro">{assessed === pulses.length ? "Pulses" : `Pulses · ${assessed} assessed`}</span>
        </span>
        <span className="wall-key" aria-hidden="true">
          <span className="pulse-legend-scale">
            {(["calm", "elevated", "severe", "critical"] as const).map((b) => (
              <span key={b} className={`intel-band-${b}`} />
            ))}
          </span>
          <span className="intel-micro">0 calm · 100 extreme</span>
        </span>
        <span className="wall-controls">
          <span className="wall-seg" role="group" aria-label="Sort">
            {SORTS.map((s) => (
              <button key={s} type="button" aria-pressed={sort === s} onClick={() => chooseSort(s)}>
                {SORT_LABEL[s]}
              </button>
            ))}
          </span>
          <span className="wall-seg" role="group" aria-label="Change period">
            {PERIODS.map((per) => (
              <button key={per} type="button" aria-pressed={period === per} onClick={() => choosePeriod(per)}>
                {per}
              </button>
            ))}
          </span>
        </span>
      </div>

      {pulses.length === 0 ? (
        <p className="intel-empty">No Pulses have been published yet. Check back soon.</p>
      ) : (
        <div ref={gridRef} className="wall-grid" style={gridStyle}>
          {items.map((it, i) => {
            const cell = spiral ? cells[i] : undefined;
            // Keyed by Pulse id (not position) so an open popover survives re-sorting and follows its tile.
            return (
              <div key={it.p.id} className="wall-cell" style={cell ? { gridRow: cell[0], gridColumn: cell[1] } : undefined}>
                <PulseTile pulse={it.p} delta={it.change} period={period} showDelta={showMoves} />
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
