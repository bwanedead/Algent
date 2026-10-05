import Popover from "@/components/Popover";
import PulseTile from "@/components/PulseTile";
import type { DailyDevelopment, DailyPulse, DailyStatement, KeyFigure, TheaterMap } from "@/lib/daily";
import { mappedNumbers } from "@/components/map/numbering";
import { shortDay } from "@/lib/daily";
import { COVERAGE_DISPLAY, safeUrl, type Coverage, type Pulse, type Snapshot } from "@/lib/intel";
import { toWallPulse, type WallPulse } from "@/lib/pulse-wall";

// Visuals for the daily report (doctrine: docs/ethos/information-ergonomics-ethos.md). Server
// components; inline SVG/CSS only. Everything renders nothing when its data is absent. Styles are in
// app/geopolitics/geopolitics.css (geo-*). Detail never reflows the page: it opens in a Popover.

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function SourceLink({ url, label }: { url: string; label?: string }) {
  const href = safeUrl(url);
  if (!href) return url ? <span className="geo-micro">{url}</span> : null;
  return (
    <a href={href} className="geo-src" target="_blank" rel="noopener noreferrer nofollow">
      {label ?? host(href)} ↗
    </a>
  );
}

const fmtNum = (v: number) => v.toLocaleString("en-GB", { maximumFractionDigits: 2 });
/** Big numbers shortened for a tile ("1.55M"); the popover keeps the exact figure. */
const fmtShort = (v: number) => (Math.abs(v) >= 10000 ? v.toLocaleString("en-GB", { notation: "compact", maximumFractionDigits: 2 }) : fmtNum(v));

// ---- Pulses -----------------------------------------------------------------------------------
function inSnapshot(snap: Snapshot | null, p: DailyPulse): { pulse: Pulse; situation: string } | null {
  if (!snap) return null;
  let byName: { pulse: Pulse; situation: string } | null = null;
  for (const sit of snap.situations)
    for (const sp of sit.pulses) {
      if (p.id && sp.id === p.id) return { pulse: sp, situation: sit.title };
      if (!byName && sp.name === p.name) byName = { pulse: sp, situation: sit.title };
    }
  return byName;
}

/** The shared Pulse object for a daily-report Pulse: the live snapshot reading when we have it, else the report's own. */
function wallPulseFor(snap: Snapshot | null, p: DailyPulse): { wall: WallPulse; note?: string } {
  const hit = inSnapshot(snap, p);
  if (hit) {
    const wall = toWallPulse(hit.pulse, hit.situation);
    const moved = p.position !== null && wall.position !== null && Math.round(p.position) !== Math.round(wall.position);
    return { wall, note: moved && p.position !== null ? `in this report: ${Math.round(p.position)}` : undefined };
  }
  const own: Pulse = {
    id: p.id,
    name: p.name,
    title: p.title || p.name,
    actors_iso2: p.actors_iso2,
    question: "",
    low_end: "",
    high_end: "",
    position: p.position,
    band: p.band,
    velocity_7d: p.change_7d,
    velocity_30d: null,
    confidence: "",
    last_assessed: "",
    evidence_through: "",
    history: [],
    rationale: "",
  };
  return { wall: toWallPulse(own, "") };
}

/** A theater's Pulses as one row of the shared tile, most severe first (position = rank). */
export function PulseTiles({ pulses, snap }: { pulses: DailyPulse[]; snap: Snapshot | null }) {
  if (pulses.length === 0) return null;
  const sorted = [...pulses].sort((a, b) => (b.position ?? -1) - (a.position ?? -1));
  return (
    <div className="geo-pulses">
      {sorted.map((p, i) => {
        const { wall, note } = wallPulseFor(snap, p);
        return <PulseTile key={`${p.id}-${i}`} pulse={wall} delta={p.change_24h} period="24h" size="s" note={note} anchor={false} />;
      })}
    </div>
  );
}

// ---- coverage ---------------------------------------------------------------------------------
/** Coverage as a tiny neutral sparkline (headlines per day, last week). Never a band colour. */
export function CoverSpark({ series, coverage, name }: { series: { day: string; count: number }[]; coverage: Coverage; name: string }) {
  const c = COVERAGE_DISPLAY[coverage];
  const week = series.slice(-7);
  const title = `Coverage ${c.label}: headlines about this theater per day`;
  if (week.length < 2) {
    return (
      <span className="geo-cov" title={title}>
        <span aria-hidden="true">{c.glyph}</span> {c.label}
      </span>
    );
  }
  const W = 56;
  const H = 16;
  const max = Math.max(1, ...week.map((s) => s.count));
  const slot = W / week.length;
  return (
    <svg className="geo-spark" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${name}: headlines per day over the last ${week.length} days; coverage ${c.label}`}>
      <title>{title}</title>
      <line x1={0} x2={W} y1={H - 0.5} y2={H - 0.5} className="geo-spark-base" />
      {week.map((s, i) => {
        const h = s.count > 0 ? Math.max(1.5, (s.count / max) * (H - 2)) : 0;
        return <rect key={i} x={i * slot} y={H - 1 - h} width={Math.max(1, slot - 1.5)} height={h} className="geo-spark-bar" />;
      })}
    </svg>
  );
}

// ---- key figures ------------------------------------------------------------------------------
function pctChange(value: number, baseline: number | null): number | null {
  return baseline !== null && baseline !== 0 ? ((value - baseline) / Math.abs(baseline)) * 100 : null;
}
const fmtPct = (p: number) => `${p > 0 ? "▲ +" : p < 0 ? "▼ −" : "◆ "}${Math.abs(p) < 10 ? Math.abs(p).toFixed(1) : Math.round(Math.abs(p))}%`;

/** Value against its baseline on one scale: the bar is the value, the tick is where it was. */
function FigureBar({ value, baseline }: { value: number; baseline: number }) {
  if (value < 0 || baseline < 0) return null;
  const max = Math.max(value, baseline);
  if (max <= 0) return null;
  return (
    <span className="geo-fig-bar" role="img" aria-label={`${fmtNum(value)} compared with ${fmtNum(baseline)}`}>
      <span className="geo-fig-fill" style={{ width: `${(value / max) * 100}%` }} />
      <span className="geo-fig-base" style={{ left: `${(baseline / max) * 100}%` }} />
    </span>
  );
}

export function KeyFigures({ figures }: { figures: KeyFigure[] }) {
  if (figures.length === 0) return null;
  return (
    <div className="geo-figs">
      {figures.map((f, i) => {
        const pct = pctChange(f.value, f.baseline);
        return (
          <Popover
            key={i}
            label={f.label}
            triggerClassName="geo-fig"
            trigger={
              <>
                <span className="geo-fig-label">{f.label}</span>
                <span className="geo-fig-value">
                  <b>{fmtShort(f.value)}</b>
                  {f.unit && <span className="geo-fig-unit">{f.unit}</span>}
                </span>
                {f.baseline !== null && (
                  <>
                    <FigureBar value={f.value} baseline={f.baseline} />
                    <span className="geo-fig-vs">
                      {pct !== null && Math.abs(pct) >= 0.5 && <span className="geo-chg">{fmtPct(pct)} </span>}
                      vs {f.baseline_label || "baseline"}
                    </span>
                  </>
                )}
              </>
            }
          >
            <div className="geo-pd">
              <p className="geo-pd-title">{f.label}</p>
              <p className="geo-pd-big">
                <b>{fmtNum(f.value)}</b> {f.unit}
              </p>
              {f.baseline !== null && (
                <p>
                  vs {f.baseline_label || "baseline"}: {fmtNum(f.baseline)}
                  {pct !== null && <span className="geo-chg"> {fmtPct(pct)}</span>}
                </p>
              )}
              <p className="geo-pd-foot">
                {f.as_of && <span className="geo-micro">as of {f.as_of}</span>}
                {f.source && <SourceLink url={f.source} />}
              </p>
            </div>
          </Popover>
        );
      })}
    </div>
  );
}

// ---- developments timeline --------------------------------------------------------------------
const ISO = /\d{4}-\d{2}-\d{2}/;
const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

/** Day of a development as YYYY-MM-DD: an ISO date in `when`, or "Sep 30" / "30 Sep" read against the report date. "" if neither. */
export function devDay(when: string, reportDate: string): string {
  const iso = when.match(ISO);
  if (iso) return Number.isNaN(new Date(`${iso[0]}T00:00:00Z`).getTime()) ? "" : iso[0];
  const rd = reportDate.match(ISO);
  if (!rd) return "";
  const m = when.match(/([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})/) ?? when.match(/(\d{1,2})\s+([A-Za-z]{3})[a-z]*/);
  if (!m) return "";
  const named = /^\d/.test(m[1]) ? { mon: m[2], day: m[1] } : { mon: m[1], day: m[2] };
  const mi = MONTHS.indexOf(named.mon.toLowerCase());
  const dd = Number(named.day);
  if (mi < 0 || dd < 1 || dd > 31) return "";
  const ry = Number(reportDate.slice(0, 4));
  const rm = Number(reportDate.slice(5, 7)) - 1;
  const year = mi > rm + 1 ? ry - 1 : ry; // "Dec 30" in a January report is last year
  const dt = new Date(Date.UTC(year, mi, dd));
  return dt.getUTCMonth() === mi ? dt.toISOString().slice(0, 10) : "";
}

function Statement({ s }: { s: DailyStatement }) {
  const who = (
    <figcaption className="geo-quote-cap">
      <span className="geo-strong">{s.who || "Unattributed"}</span>
      {s.role && <span className="geo-muted">, {s.role}</span>}
      {s.when && <span className="geo-micro"> · {s.when}</span>}
      {s.source && (
        <>
          {" "}
          <SourceLink url={s.source} />
        </>
      )}
    </figcaption>
  );
  return s.quote ? (
    <figure className="geo-quote">
      <blockquote>
        <p>“{s.said}”</p>
      </blockquote>
      {who}
    </figure>
  ) : (
    <figure className="geo-quote geo-quote-para">
      <p>
        <span className="geo-strong">{s.who || "A source"}</span> said that {s.said}
      </p>
      {who}
    </figure>
  );
}

/** Everything about one development, for the popover. */
function DevelopmentDetail({ d }: { d: DailyDevelopment }) {
  const verified = d.verification === "researched";
  const where = d.where || [d.place?.name, d.place?.country].filter(Boolean).join(", ");
  return (
    <div className="geo-pd">
      <p className="geo-pd-title">{d.headline}</p>
      <p className="geo-pd-meta">
        <span className={`geo-v ${verified ? "is-solid" : "is-hollow"}`} aria-hidden="true" />
        <span>{verified ? "Researched" : "Reported, not independently checked"}</span>
        {[d.when, where].filter(Boolean).length > 0 && <span className="geo-micro"> · {[d.when, where].filter(Boolean).join(" · ")}</span>}
      </p>
      {d.detail && <p className="geo-pd-text">{d.detail}</p>}
      {d.statements.map((s, i) => (
        <Statement key={i} s={s} />
      ))}
      {d.significance && (
        <p className="geo-pd-text">
          <span className="geo-micro">Why it matters</span> {d.significance}
        </p>
      )}
      {d.sources.length > 0 && (
        <p className="geo-pd-foot">
          {d.sources.map((u, i) => (
            <SourceLink key={i} url={u} />
          ))}
        </p>
      )}
    </div>
  );
}

/** Developments as a vertical timeline, newest day first: one line each, detail in a popover. The mark is
 *  solid when researched, hollow when reported, and carries the map's number when the map shows it. */
export function DevelopmentTimeline({ developments, map, reportDate }: { developments: DailyDevelopment[]; map: TheaterMap | null; reportDate: string }) {
  if (developments.length === 0) return null;
  const mapped = mappedNumbers(map, developments.length);
  const rows = developments.map((d, i) => ({ d, i, day: devDay(d.when, reportDate) }));
  rows.sort((a, b) => (a.day < b.day ? 1 : a.day > b.day ? -1 : a.i - b.i));
  let prev = "\u0000";
  return (
    <ol className="geo-tl">
      {rows.map(({ d, i, day }) => {
        const label = day && day !== prev ? shortDay(day) : "";
        prev = day;
        const verified = d.verification === "researched";
        const n = mapped.get(i) ?? null;
        return (
          <li key={i} className="geo-ev">
            <span className="geo-ev-day">{label}</span>
            <span className={`geo-ev-mark ${verified ? "is-solid" : "is-hollow"}${n !== null ? " has-n" : ""}`} title={verified ? "Researched" : "Reported, not independently checked"}>
              {n ?? ""}
            </span>
            <Popover
              label={d.headline}
              triggerClassName="geo-ev-btn"
              trigger={
                <>
                  <span className="geo-ev-head">{d.headline}</span>
                  <span className="geo-more" aria-hidden="true">
                    ›
                  </span>
                </>
              }
            >
              <DevelopmentDetail d={d} />
            </Popover>
          </li>
        );
      })}
    </ol>
  );
}
