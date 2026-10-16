"use client";

// Our own trackers compared (daily visual kind "tracker_compare" with a `spec`; contract: backend agents/intel/tracker_compare_spec.py).
// Two to six of the instruments we measure on one interactive chart, drawn from the stored readings the spec carries (no number
// in it came from a model). "Index" shows every line as 100 where all of them have begun, so unlike units can be compared by
// movement; "Raw" gives each line its own panel on the same time axis, in its own unit (never two axes on one plot). Lines are
// labelled at their ends; hover or touch-drag puts a crosshair on the date and reads every line there; the day's developments
// are flags on the time axis (tap one for its words and sources). Chips under the chart hide a line. Pure SVG, sized to its width.
// Reduced motion: nothing here animates. If the spec cannot load, the server-drawn still takes its place. Client-safe imports only.

import { useEffect, useMemo, useRef, useState } from "react";

import { allDays, dayOf, dodge, fmt, indexed, isoOf, nearestDay, readingAt, ticks, commonStart, type Pt } from "@/components/trackerChart";
import { dateParts } from "@/components/timelineLayout";
import { useSpec } from "@/components/useSpec";
import { parseTrackerCompare, type TrackerCompareSpec, type TrackerLine, type TrackerMarker } from "@/lib/visualSpecs";

import "./nativeviz.css";

const fmtDate = (iso: string) => {
  const d = dateParts(iso);
  return `${d.day} ${d.year}`;
};
const hostOf = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
};
const short = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

type Mode = "index" | "raw";
type Drawn = { line: TrackerLine; pts: Pt[]; k: number };

const PAD = { l: 38, t: 16, b: 24 };

function Chart({ spec }: { spec: TrackerCompareSpec }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(360);
  const [mode, setMode] = useState<Mode>("index");
  const [hidden, setHidden] = useState<string[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [flag, setFlag] = useState<TrackerMarker | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    setWidth(Math.round(el.getBoundingClientRect().width) || 360);
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((es) => setWidth(Math.round(es[0].contentRect.width) || 360));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const start = useMemo(() => commonStart(spec.series), [spec]);
  const all = useMemo<Drawn[]>(() => spec.series.map((line, k) => ({ line, pts: indexed(line, start), k })).filter((d) => d.pts.length >= 2), [spec, start]);
  const shown = all.filter((d) => !hidden.includes(d.line.id));
  const narrow = width < 520;
  const right = narrow ? 74 : 132;
  const x0 = Math.min(...all.map((d) => d.pts[0].day));
  const x1 = Math.max(...all.map((d) => d.pts[d.pts.length - 1].day));
  const plotW = Math.max(60, width - PAD.l - right);
  const X = (day: number) => PAD.l + ((day - x0) / Math.max(1, x1 - x0)) * plotW;

  // Panels: one shared plot (index) or one per line (raw). Each has its own y scale.
  const panelH = mode === "index" ? Math.round(Math.min(330, Math.max(230, width * 0.6))) : 74;
  const panels = mode === "index" ? [shown] : shown.map((d) => [d]);
  const val = (d: Drawn, p: Pt) => (mode === "index" ? p.idx : p.raw);
  const scales = panels.map((ds, pi) => {
    const vs = ds.flatMap((d) => d.pts.map((p) => val(d, p))).concat(mode === "index" ? [100] : []);
    let lo = Math.min(...vs);
    let hi = Math.max(...vs);
    const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.05 || 1;
    lo -= pad;
    hi += pad;
    const top = PAD.t + panels.slice(0, pi).length * (panelH + 12);
    const Y = (v: number) => top + (hi - v) / (hi - lo) * (panelH - 8) + 4;
    return { ds, lo, hi, top, Y, ticks: ticks(lo, hi, mode === "index" ? 4 : 2) };
  });
  const height = PAD.t + panels.length * (panelH + 12) + PAD.b - 12;
  const days = allDays(shown.map((d) => d.pts));
  const flags = spec.markers.filter((m) => dayOf(m.date) >= x0 && dayOf(m.date) <= x1);

  const at = (clientX: number, el: SVGSVGElement) => {
    const r = el.getBoundingClientRect();
    const day = x0 + ((clientX - r.left - PAD.l) / plotW) * (x1 - x0);
    if (days.length) setCursor(nearestDay(days, Math.min(x1, Math.max(x0, day))));
  };

  const day = cursor ?? x1;
  const rows = shown.map((d) => ({ d, p: readingAt(d.pts, day) }));
  const nearFlag = flag ?? flags.find((m) => cursor !== null && Math.abs(dayOf(m.date) - cursor) <= Math.max(1, (x1 - x0) / 60)) ?? null;

  if (all.length === 0) return <p className="nv-hint">{spec.caption}</p>;
  return (
    <div className="nc" ref={wrap}>
      <div className="nv-bar nc-modes" role="group" aria-label="Scale">
        <button type="button" className="nv-btn" aria-pressed={mode === "index"} onClick={() => setMode("index")}>
          Index (100 = {fmtDate(start)})
        </button>
        <button type="button" className="nv-btn" aria-pressed={mode === "raw"} onClick={() => setMode("raw")}>
          Raw values
        </button>
      </div>
      <svg
        className="nc-svg"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Chart: ${spec.title || spec.caption}. The readings are listed under the chart.`}
        onPointerMove={(e) => at(e.clientX, e.currentTarget)}
        onPointerDown={(e) => {
          setFlag(null);
          at(e.clientX, e.currentTarget);
        }}
        onPointerLeave={(e) => e.pointerType === "mouse" && setCursor(null)}
      >
        {scales.map((sc, pi) => (
          <g key={pi}>
            {sc.ticks.map((t) => (
              <g key={t}>
                <line x1={PAD.l} x2={PAD.l + plotW} y1={sc.Y(t)} y2={sc.Y(t)} className={`nc-grid${mode === "index" && t === 100 ? " is-base" : ""}`} />
                <text x={PAD.l - 6} y={sc.Y(t) + 4} textAnchor="end" className="nc-tick">
                  {fmt(t)}
                </text>
              </g>
            ))}
            {mode === "raw" && (
              <text x={PAD.l} y={sc.top - 3} className="nc-panel">
                {sc.ds[0].line.label} · {sc.ds[0].line.unit}
              </text>
            )}
            {sc.ds.map((d) => {
              const pts = d.pts.map((p) => `${X(p.day).toFixed(1)},${sc.Y(val(d, p)).toFixed(1)}`).join(" ");
              return <polyline key={d.line.id} points={pts} className={`nc-line nc-c${d.k % 6}`} fill="none" />;
            })}
          </g>
        ))}
        {/* direct labels at the line ends (index: spread so none overlaps; raw: beside each panel's line) */}
        {scales.flatMap((sc) => {
          const ends = sc.ds.map((d) => sc.Y(val(d, d.pts[d.pts.length - 1])));
          const ys = mode === "index" ? dodge(ends, 13, sc.top + 6, sc.top + panelH - 4) : ends;
          return sc.ds.map((d, i) => {
            const last = d.pts[d.pts.length - 1];
            return (
              <g key={d.line.id} className={`nc-end nc-c${d.k % 6}`}>
                <circle cx={X(last.day)} cy={sc.Y(val(d, last))} r={3.2} className="nc-dot" />
                <text x={X(last.day) + 8} y={ys[i] + 4} className="nc-lbl">
                  {short(d.line.label, narrow ? 10 : 20)} {fmt(val(d, last))}
                </text>
              </g>
            );
          });
        })}
        {flags.map((m) => (
          <g key={m.date + m.label} className="nc-flag" onClick={(e) => { e.stopPropagation(); setFlag(flag === m ? null : m); setCursor(dayOf(m.date)); }} role="button" tabIndex={0}
            aria-label={`${fmtDate(m.date)}: ${m.label}`}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setFlag(flag === m ? null : m); setCursor(dayOf(m.date)); } }}>
            <line x1={X(dayOf(m.date))} x2={X(dayOf(m.date))} y1={PAD.t} y2={height - PAD.b} className="nc-flagline" />
            <path d={`M${X(dayOf(m.date)) - 5},${height - PAD.b + 11} l5,-9 l5,9 z`} className="nc-flagmark" />
            <rect x={X(dayOf(m.date)) - 14} y={PAD.t} width={28} height={height - PAD.t} className="nc-hit" />
          </g>
        ))}
        {cursor !== null && (
          <g pointerEvents="none">
            <line x1={X(cursor)} x2={X(cursor)} y1={PAD.t} y2={height - PAD.b} className="nc-cursor" />
            {scales.flatMap((sc) =>
              sc.ds.map((d) => {
                const p = readingAt(d.pts, cursor);
                return p ? <circle key={d.line.id} cx={X(p.day)} cy={sc.Y(val(d, p))} r={4} className={`nc-dot nc-c${d.k % 6}`} /> : null;
              }),
            )}
          </g>
        )}
        <text x={PAD.l} y={height - 6} className="nc-tick">{fmtDate(isoOf(x0))}</text>
        <text x={PAD.l + plotW} y={height - 6} textAnchor="end" className="nc-tick">{fmtDate(isoOf(x1))}</text>
      </svg>

      <div className="nv-detail nc-read" aria-live="polite">
        <p className="nv-head">{cursor === null ? `Latest · ${fmtDate(isoOf(x1))}` : fmtDate(isoOf(cursor))}</p>
        <ul className="nc-rows">
          {rows.map(({ d, p }) => (
            <li key={d.line.id} className={`nc-c${d.k % 6}`}>
              <i aria-hidden="true" />
              <span className="nc-name">{d.line.label}</span>
              <b>{p ? (mode === "index" ? fmt(p.idx) : `${fmt(p.raw)} ${d.line.unit}`) : "not yet measured"}</b>
              {p && mode === "index" && <span className="nc-raw">{fmt(p.raw)} {d.line.unit}</span>}
              {p && isoOf(day) !== p.date && <span className="nc-raw">as of {fmtDate(p.date)}</span>}
            </li>
          ))}
        </ul>
        {nearFlag && (
          <div className="nc-note">
            <p className="nv-text"><b>{fmtDate(nearFlag.date)}</b> {nearFlag.label}</p>
            {nearFlag.sources.length > 0 && (
              <p className="nv-src">
                {nearFlag.sources.map((s, i) => (s.url ? <a key={i} href={s.url} className="geo-src" target="_blank" rel="noopener noreferrer nofollow">{s.label || hostOf(s.url)} ↗</a> : <span key={i} className="geo-micro">{s.label}</span>))}
              </p>
            )}
          </div>
        )}
      </div>

      <ul className="nc-chips" aria-label="Lines (tap to hide or show)">
        {all.map((d) => (
          <li key={d.line.id}>
            <button type="button" className={`nc-chip nc-c${d.k % 6}`} aria-pressed={!hidden.includes(d.line.id)}
              onClick={() => setHidden(hidden.includes(d.line.id) ? hidden.filter((h) => h !== d.line.id) : shown.length > 1 ? [...hidden, d.line.id] : hidden)}>
              <i aria-hidden="true" />
              {d.line.label}
            </button>
          </li>
        ))}
      </ul>
      <details className="nv-all">
        <summary>The readings and where they come from</summary>
        <ul className="nc-srclist">
          {spec.series.map((s) => (
            <li key={s.id}>
              <b>{s.label}</b>: {fmt(s.points[0][1])} on {fmtDate(s.points[0][0])} to {fmt(s.points[s.points.length - 1][1])} {s.unit} on {fmtDate(s.points[s.points.length - 1][0])}.{" "}
              {s.sourceUrl ? <a href={s.sourceUrl} className="geo-src" target="_blank" rel="noopener noreferrer nofollow">{s.source} ↗</a> : <span className="geo-micro">{s.source}</span>}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

export default function NativeTrackerCompare({ src, preview, title, caption }: { src: string; preview: string; title: string; caption: string }) {
  const { host, spec, failed } = useSpec(src, parseTrackerCompare);
  const still = preview ? <img className="nv-still" src={preview} alt={title || caption || "Trackers compared"} loading="lazy" /> : null;
  return <div className="nv-host" ref={host}>{spec ? <Chart spec={spec} /> : failed ? still : <div className="nv-wait">{still}</div>}</div>;
}
