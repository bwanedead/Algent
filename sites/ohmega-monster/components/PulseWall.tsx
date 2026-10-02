"use client";

// The /pulses scanner: a dense wall of uniform tiles (name, number, meter), sortable, with one
// overlay popover for detail. Sort/period live in the URL (?sort=&period=) so a view can be shared.
// Pure ordering/layout maths is in lib/pulse-wall.ts; this file owns state, DOM and focus.

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { BAND_LABEL, deltaClass, fmtDelta } from "@/lib/band";
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
  type WallItem,
  type WallPulse,
} from "@/lib/pulse-wall";

import PulseSpectrum from "./PulseSpectrum";

const GAP = 6;
const MIN_TILE = 150;
const MIN_TILE_PHONE = 104;
const SPIRAL_MIN_COLS = 4; // narrower than this the spiral has no centre worth speaking of: plain list order
const HASH_PREFIX = "pulse-";
const day = (at: string) => at.slice(0, 10);

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

function Meter({ item }: { item: WallItem }) {
  const pos = item.p.position;
  if (pos === null) return <span className="wall-meter wall-meter-empty" aria-hidden="true" />;
  const clamp = (v: number) => Math.min(100, Math.max(0, v));
  return (
    <span className="wall-meter" aria-hidden="true">
      <span className="wall-fill" style={{ width: `${clamp(pos)}%` }} />
      {item.from !== null && <span className="wall-ghost" style={{ left: `${clamp(item.from)}%` }} />}
      <span className="wall-mark" style={{ left: `${clamp(pos)}%` }} />
    </span>
  );
}

function History({ p }: { p: WallPulse }) {
  const pts = p.history.slice(-40);
  if (pts.length === 0) return null;
  const W = 320;
  const H = 56;
  const pad = 5;
  const y = (v: number) => pad + (1 - Math.min(100, Math.max(0, v)) / 100) * (H - pad * 2);
  const times = pts.map((h) => Date.parse(h.at));
  const timed = pts.length > 1 && times.every(Number.isFinite) && times[times.length - 1] > times[0];
  const x = (i: number) =>
    pts.length === 1 ? W - pad : pad + (timed ? (times[i] - times[0]) / (times[times.length - 1] - times[0]) : i / (pts.length - 1)) * (W - pad * 2);
  const xy = pts.map((h, i) => [x(i), y(h.position)] as const);
  const d = xy.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join(" ");
  const last = xy[xy.length - 1];
  return (
    <figure className={`pulse-hist wall-hist intel-band-${p.band}`}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${p.name}: ${pts.length} readings, ${day(pts[0].at)} to ${day(pts[pts.length - 1].at)}`}>
        {[25, 50, 75].map((g) => (
          <line key={g} x1={pad} x2={W - pad} y1={y(g)} y2={y(g)} className="pulse-hist-grid" />
        ))}
        {pts.length > 1 && <path d={d} className="pulse-hist-line" />}
        <circle cx={last[0]} cy={last[1]} r={3} className="pulse-hist-dot" />
      </svg>
      <figcaption className="intel-micro">
        <span>{day(pts[0].at)}</span>
        <span>{pts.length > 1 ? day(pts[pts.length - 1].at) : ""}</span>
      </figcaption>
    </figure>
  );
}

function Popover({ item, period, popRef, onClose }: { item: WallItem; period: Period; popRef: React.RefObject<HTMLDivElement>; onClose: () => void }) {
  const { p, change, from } = item;
  const titleId = `wall-pop-title-${p.id}`;
  const assessed = p.position !== null;
  return (
    <div ref={popRef} className="wall-pop" role="dialog" aria-modal="false" aria-labelledby={titleId} tabIndex={-1}>
      <div className="wall-pop-head">
        <div>
          <h2 id={titleId} className="wall-pop-title">
            {p.name}
          </h2>
          {p.situation && <span className="intel-micro">{p.situation}</span>}
        </div>
        <button type="button" className="wall-pop-x" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
      {p.question && <p className="pulse-q">{p.question}</p>}
      <div className="pulse-spec-wrap">
        <PulseSpectrum position={p.position} variant="full" />
        {(p.low_end || p.high_end) && (
          <div className="pulse-ends">
            <p>
              <span className="intel-micro">0 · calm</span>
              {p.low_end || "—"}
            </p>
            <p className="pulse-end-hi">
              <span className="intel-micro">100 · extreme</span>
              {p.high_end || "—"}
            </p>
          </div>
        )}
      </div>
      <p className="wall-pop-stats">
        <span className={assessed ? "intel-num" : "intel-num intel-muted"}>{assessed ? Math.round(p.position as number) : "—"}</span>
        <span className={`intel-chip intel-band-${p.band}`}>{BAND_LABEL[p.band]}</span>
        <span className={`intel-delta intel-delta-${deltaClass(change)}`} title={from !== null ? `Was ${Math.round(from)} ${period} ago` : "No reading that far back"}>
          {fmtDelta(change)} <span className="intel-micro">{period}</span>
        </span>
      </p>
      <History p={p} />
      {(p.last_assessed || p.confidence) && (
        <p className="intel-micro wall-pop-foot">
          {p.last_assessed && <>Updated {day(p.last_assessed)}</>}
          {p.confidence && <> · {p.confidence} confidence</>}
        </p>
      )}
      {p.rationale && <p className="wall-pop-why">{p.rationale}</p>}
    </div>
  );
}

export default function PulseWall({ pulses, asOf, asOfLabel }: { pulses: WallPulse[]; asOf: string; asOfLabel: string }) {
  const [sort, setSort] = useState<SortKey>(DEFAULT_SORT);
  const [period, setPeriod] = useState<Period>(DEFAULT_PERIOD);
  const [openId, setOpenId] = useState<string | null>(null);
  const [cols, setCols] = useState(0);
  const gridRef = useRef<HTMLDivElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  // ---- URL <-> state ----------------------------------------------------------------------
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setSort(parseSort(q.get("sort")));
    setPeriod(parsePeriod(q.get("period")));
    const fromHash = () => {
      let h = window.location.hash.slice(1);
      try {
        h = decodeURIComponent(h);
      } catch {
        /* keep the raw hash */
      }
      if (h.startsWith(HASH_PREFIX)) {
        const id = h.slice(HASH_PREFIX.length);
        if (pulses.some((p) => p.id === id)) setOpenId(id);
      }
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, [pulses]);

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

  // ---- popover ----------------------------------------------------------------------------
  const open = openId === null ? null : items.find((i) => i.p.id === openId) ?? null;
  const close = useCallback(() => {
    setOpenId(null);
    const back = returnFocus.current;
    returnFocus.current = null;
    if (back && document.contains(back)) back.focus({ preventScroll: true });
  }, []);

  const place = useCallback(() => {
    const pop = popRef.current;
    const tile = openId === null ? null : document.getElementById(`${HASH_PREFIX}${openId}`);
    if (!pop || !tile) return;
    const r = tile.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const pw = pop.offsetWidth;
    const ph = pop.offsetHeight;
    const x = Math.min(Math.max(8, r.left), Math.max(8, vw - pw - 8));
    let y = r.bottom + 6;
    if (y + ph > vh - 8) y = r.top - ph - 6;
    if (y < 8) y = Math.max(8, vh - ph - 8);
    pop.style.setProperty("--pop-x", `${Math.round(x)}px`);
    pop.style.setProperty("--pop-y", `${Math.round(y)}px`);
    pop.dataset.ready = "1";
  }, [openId]);

  const openKey = open ? open.p.id : null;
  useEffect(() => {
    if (openKey === null) return;
    place();
    popRef.current?.querySelector<HTMLElement>(".wall-pop-x")?.focus({ preventScroll: true });
  }, [openKey, place]);

  // Sorting can move the selected tile; follow it.
  useEffect(() => {
    if (openKey !== null) place();
  }, [sort, period, cols, openKey, place]);

  useEffect(() => {
    if (openId === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    const onDown = (e: PointerEvent) => {
      const t = e.target as Element | null;
      if (t?.closest(".wall-pop") || t?.closest(".wall-tile")) return; // a tile click switches or toggles
      close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, { passive: true });
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place);
    };
  }, [openId, close, place]);

  const onTile = (e: React.MouseEvent<HTMLButtonElement>, id: string) => {
    if (openId === id) return close();
    returnFocus.current = e.currentTarget;
    setOpenId(id);
  };

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
            const { p } = it;
            const pos = p.position === null ? null : Math.round(p.position);
            const cell = spiral ? cells[i] : undefined;
            return (
              <button
                key={`${p.id}-${i}`}
                id={`${HASH_PREFIX}${p.id}`}
                type="button"
                className={`wall-tile intel-band-${p.band}${openId === p.id ? " is-open" : ""}`}
                style={cell ? { gridRow: cell[0], gridColumn: cell[1] } : undefined}
                aria-haspopup="dialog"
                aria-expanded={openId === p.id}
                aria-label={pos === null ? `${p.name}: not yet assessed` : `${p.name}: ${pos} out of 100, ${BAND_LABEL[p.band].toLowerCase()}`}
                onClick={(e) => onTile(e, p.id)}
              >
                <span className="wall-name">{p.name}</span>
                <span className="wall-row">
                  <span className={pos === null ? "wall-num wall-num-none" : "wall-num"}>{pos === null ? "—" : pos}</span>
                  {showMoves && <span className={`wall-delta intel-delta-${deltaClass(it.change)}`}>{fmtDelta(it.change)}</span>}
                </span>
                <Meter item={it} />
              </button>
            );
          })}
        </div>
      )}

      {open && (
        <>
          <div className="wall-scrim" aria-hidden="true" />
          <Popover key={open.p.id} item={open} period={period} popRef={popRef} onClose={close} />
        </>
      )}
    </>
  );
}
