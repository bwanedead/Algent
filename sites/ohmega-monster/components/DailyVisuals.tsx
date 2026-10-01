import type { DailyDevelopment, KeyFigure, TheaterMap } from "@/lib/daily";
import { safeUrl } from "@/lib/intel";

import { DayBars } from "./IntelViz";

// Visuals for the daily report. Each renders nothing when its data is absent. Server components,
// inline SVG/CSS only; colours come from the site tokens so both displays work.

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function SourceLink({ url, label }: { url: string; label?: string }) {
  const href = safeUrl(url);
  if (!href) return url ? <span className="intel-micro">{url}</span> : null;
  return (
    <a href={href} className="daily-src" target="_blank" rel="noopener noreferrer nofollow">
      {label ?? host(href)} ↗
    </a>
  );
}

const fmtNum = (v: number) => v.toLocaleString("en-GB", { maximumFractionDigits: 2 });

// ---- key figures ----------------------------------------------------------------------------
function FigureBar({ value, baseline }: { value: number; baseline: number }) {
  if (value < 0 || baseline < 0) return null;
  const max = Math.max(value, baseline);
  if (max <= 0) return null;
  const v = (value / max) * 100;
  const b = (baseline / max) * 100;
  return (
    <span className="daily-fig-bar" role="img" aria-label={`${fmtNum(value)} compared with ${fmtNum(baseline)}`}>
      <span className="daily-fig-fill" style={{ width: `${v}%` }} />
      <span className="daily-fig-base" style={{ left: `${b}%` }} />
    </span>
  );
}

export function KeyFigureTiles({ figures }: { figures: KeyFigure[] }) {
  if (figures.length === 0) return null;
  return (
    <div className="daily-block">
      <h4 className="intel-sub">Key figures</h4>
      <div className="daily-figs">
        {figures.map((f, i) => (
          <div key={i} className="daily-fig">
            <span className="intel-micro daily-fig-label">{f.label}</span>
            <span className="daily-fig-value">
              <b className="intel-tab">{fmtNum(f.value)}</b>
              {f.unit && <span className="daily-fig-unit">{f.unit}</span>}
            </span>
            {f.baseline !== null && (
              <>
                <FigureBar value={f.value} baseline={f.baseline} />
                <span className="intel-micro daily-fig-vs">
                  vs {f.baseline_label || "baseline"} · {fmtNum(f.baseline)}
                </span>
              </>
            )}
            {(f.source || f.as_of) && (
              <span className="daily-fig-src">
                {f.source && <SourceLink url={f.source} />}
                {f.as_of && <span className="intel-micro">as of {f.as_of}</span>}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- theater map ----------------------------------------------------------------------------
/** The map's numbers index the developments. Zero-based unless the data plainly counts from 1. */
export function mapIndexBase(map: TheaterMap, devCount: number): 0 | 1 {
  const ns = map.points.map((p) => p.n).filter((n): n is number => n !== null);
  return !ns.includes(0) && ns.includes(devCount) ? 1 : 0;
}

export function TheaterMapSlot({ map, developments }: { map: TheaterMap | null; developments: DailyDevelopment[] }) {
  if (map === null || map === undefined) return null;
  const base = mapIndexBase(map, developments.length);
  const r = map.width * 0.022;
  const items = map.points.map((p, i) => {
    const di = p.n === null ? -1 : p.n - base;
    const dev = di >= 0 && di < developments.length ? developments[di] : null;
    return { p, num: dev ? di + 1 : p.n ?? i + 1, headline: dev ? dev.headline : p.label };
  });
  const sorted = [...items].sort((a, b) => a.num - b.num);
  return (
    <figure className="daily-map">
      <svg viewBox={`0 0 ${map.width} ${map.height}`} role="img" aria-label={`Map of developments. ${items.length} marked place${items.length === 1 ? "" : "s"}, listed below.`} className="daily-map-svg">
        <rect width={map.width} height={map.height} className="daily-map-sea" />
        {map.countries.map((c, i) => (
          <path key={i} d={c.d} className="daily-map-land">
            {c.name && <title>{c.name}</title>}
          </path>
        ))}
        {items.map(({ p, num, headline }, i) => (
          <g key={i} transform={`translate(${p.x.toFixed(1)} ${p.y.toFixed(1)})`} className={p.verification === "researched" ? "daily-pt daily-pt-solid" : "daily-pt daily-pt-hollow"}>
            <title>{[headline, p.date, p.verification === "researched" ? "researched" : "reported"].filter(Boolean).join(" · ")}</title>
            <circle r={r} strokeWidth={r * 0.18} />
            <text textAnchor="middle" dy="0.35em" fontSize={r * 1.15}>
              {num}
            </text>
          </g>
        ))}
      </svg>
      {sorted.length > 0 && (
        <ol className="daily-map-list">
          {sorted.map(({ p, num, headline }, i) => (
            <li key={i}>
              <span className={`daily-map-n ${p.verification === "researched" ? "is-solid" : "is-hollow"}`}>{num}</span>
              <span className="daily-map-what">
                {headline || "Development"}
                {(p.label && p.label !== headline) || p.date ? <span className="intel-micro"> {[p.label !== headline ? p.label : "", p.date].filter(Boolean).join(" · ")}</span> : null}
              </span>
            </li>
          ))}
        </ol>
      )}
      <figcaption className="intel-micro daily-map-cap">
        <span className="daily-map-key">
          <span className="daily-map-n is-solid" aria-hidden="true" /> researched
        </span>
        <span className="daily-map-key">
          <span className="daily-map-n is-hollow" aria-hidden="true" /> reported
        </span>
        {map.credit && <span className="daily-map-credit">{map.credit}</span>}
      </figcaption>
    </figure>
  );
}

// ---- coverage sparkline ---------------------------------------------------------------------
export function CoverageSpark({ series, name }: { series: { day: string; count: number }[]; name: string }) {
  const week = series.slice(-7);
  if (week.length < 2) return null;
  return (
    <span className="daily-cov-spark" title="Headlines about this theater, per day, over the last week">
      <DayBars series={week} label={`${name}: headlines per day, last ${week.length} days`} />
      <span className="intel-micro">headlines/day</span>
    </span>
  );
}

// ---- developments timeline ------------------------------------------------------------------
const ISO = /\d{4}-\d{2}-\d{2}/;
const DAY_MS = 86400000;
const shortDay = (d: string) => new Date(`${d}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

/** Day of a development as YYYY-MM-DD: an ISO date in `when`, or "Sep 30" / "30 Sep" read against the report date. "" if neither. */
export function devDay(when: string, reportDate: string): string {
  const iso = when.match(ISO);
  if (iso) return Number.isNaN(new Date(`${iso[0]}T00:00:00Z`).getTime()) ? "" : iso[0];
  const rd = reportDate.match(ISO);
  if (!rd) return "";
  const m = when.match(/([A-Za-z]{3})[a-z]*.?s+(d{1,2})/) ?? when.match(/(d{1,2})s+([A-Za-z]{3})[a-z]*/);
  if (!m) return "";
  const named = /^d/.test(m[1]) ? { mon: m[2], day: m[1] } : { mon: m[1], day: m[2] };
  const mi = MONTHS.indexOf(named.mon.toLowerCase());
  const dd = Number(named.day);
  if (mi < 0 || dd < 1 || dd > 31) return "";
  const ry = Number(reportDate.slice(0, 4));
  const rm = Number(reportDate.slice(5, 7)) - 1;
  const year = mi > rm + 1 ? ry - 1 : ry; // "Dec 30" in a January report is last year
  const dt = new Date(Date.UTC(year, mi, dd));
  return dt.getUTCMonth() === mi ? dt.toISOString().slice(0, 10) : "";
}

export function DevTimeline({ developments, reportDate }: { developments: DailyDevelopment[]; reportDate: string }) {
  const byDay = new Map<string, DailyDevelopment[]>();
  for (const d of developments) {
    const k = devDay(d.when, reportDate);
    if (k) byDay.set(k, [...(byDay.get(k) ?? []), d]);
  }
  if (byDay.size < 2) return null;
  const keys = Array.from(byDay.keys()).sort();
  const first = new Date(`${keys[0]}T00:00:00Z`).getTime();
  const last = new Date(`${keys[keys.length - 1]}T00:00:00Z`).getTime();
  const span = Math.round((last - first) / DAY_MS);
  // A short run shows every calendar day (gaps included); a long one only the days that had developments.
  const days = span <= 13 ? Array.from({ length: span + 1 }, (_, i) => new Date(first + i * DAY_MS).toISOString().slice(0, 10)) : keys;
  return (
    <div className="daily-tl" role="group" aria-label="Days with developments">
      <ol>
        {days.map((day) => {
          const list = byDay.get(day) ?? [];
          return (
            <li key={day} className={list.length ? "has" : "gap"} title={list.length ? `${shortDay(day)}: ${list.length} development${list.length === 1 ? "" : "s"}` : undefined}>
              <span className="daily-tl-dots">
                {list.map((d, i) => (
                  <i key={i} className={d.verification === "researched" ? "is-solid" : "is-hollow"} />
                ))}
              </span>
              <span className="intel-micro">{shortDay(day)}</span>
            </li>
          );
        })}
      </ol>
      <span className="intel-micro daily-tl-key">● researched · ○ reported</span>
    </div>
  );
}
