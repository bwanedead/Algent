import type { CSSProperties } from "react";

import Popover from "@/components/Popover";
import { claimOf } from "@/lib/daily";
import type { Dossier, DossierForecast, IndicatorRow } from "@/lib/dossier";
import { dayLabel, isoDay } from "@/lib/dossier-view";
import type { IndicatorStatus } from "@/lib/intel";

import { Anchor, Overflow, Section } from "./parts";

// "Where it's heading": forecasts as probability bars on one 0-100 axis, resolved ones with their
// outcome; indicators as a heat-strip of dots over the same dates for every row; then the way out to
// related theaters, reports and briefs. Colour is not used for meaning here: shape and fill carry
// status (hollow / half / solid), and the accent marks only what changed in the latest report.

const FORECASTS_SHOWN = 5;
const RESOLVED_SHOWN = 4;
const INDICATORS_SHOWN = 6;
const STRIP_DAYS = 14;

// ---- forecasts --------------------------------------------------------------------------------
function PBar({ p }: { p: number }) {
  return (
    <span className="th-pbar" role="img" aria-label={`${p} percent on a scale of 0 to 100`}>
      <span className="th-pbar-fill" style={{ width: `${p}%` }} />
    </span>
  );
}

function OpenRow({ f }: { f: DossierForecast }) {
  return (
    <li className="th-fc">
      <span className="th-fc-p">{f.probability}%</span>
      <span className="th-fc-text">{f.statement}</span>
      <PBar p={f.probability} />
      {f.horizon && <span className="th-fc-h">{f.horizon}</span>}
    </li>
  );
}

const OUTCOME = { yes: { glyph: "✓", word: "happened" }, no: { glyph: "✗", word: "did not happen" }, void: { glyph: "○", word: "void" } } as const;

function ResolutionDetail({ f }: { f: DossierForecast }) {
  const res = f.resolution ?? {};
  const known = ["outcome", "resolved_at", "evidence"];
  const extra = Object.entries(res).filter(([k]) => !known.includes(k));
  return (
    <div className="geo-pd">
      <p className="geo-pd-title">{f.statement}</p>
      <p className="geo-pd-meta">
        We said {f.probability}%{res.resolved_at ? ` · resolved ${dayLabel(isoDay(res.resolved_at) || res.resolved_at)}` : ""}
        {f.horizon ? ` · horizon ${f.horizon}` : ""}
      </p>
      {res.evidence && <p className="geo-pd-text">{res.evidence}</p>}
      {extra.map(([k, v]) => (
        <p key={k} className="geo-pd-text">
          <span className="geo-micro">{k.replace(/_/g, " ")}</span> {v}
        </p>
      ))}
    </div>
  );
}

function ResolvedRow({ f }: { f: DossierForecast }) {
  const o = OUTCOME[f.status === "yes" || f.status === "no" ? f.status : "void"];
  return (
    <li className="th-res">
      <Popover
        label={f.statement}
        triggerClassName="th-res-btn"
        trigger={
          <>
            <span className="th-chip">
              <span aria-hidden="true">{o.glyph}</span> {o.word}
            </span>
            <span className="th-res-text">{f.statement}</span>
            <span className="th-res-p">we said {f.probability}%</span>
          </>
        }
      >
        <ResolutionDetail f={f} />
      </Popover>
    </li>
  );
}

// ---- indicators -------------------------------------------------------------------------------
const RANK: Record<IndicatorStatus, number> = { observed: 2, emerging: 1, "not seen": 0 };
const STATUS_WORD: Record<IndicatorStatus, string> = { observed: "observed", emerging: "emerging", "not seen": "not seen" };

function IndicatorLine({ row, days }: { row: IndicatorRow; days: string[] }) {
  const at = new Map(row.history.map((h) => [isoDay(h.date), h.status]));
  const now = row.history[row.history.length - 1];
  const prev = row.history.length > 1 ? row.history[row.history.length - 2] : null;
  const changed = prev !== null && prev.status !== now.status;
  return (
    <li className="th-ind">
      <span className="th-ind-signal">{row.signal}</span>
      <span className="th-ind-strip" role="img" aria-label={`${row.signal}: ${STATUS_WORD[now.status]} now${changed && prev ? `, was ${STATUS_WORD[prev.status]}` : ""}`}>
        {days.map((d, i) => {
          const st = at.get(d);
          const isNow = st !== undefined && i === days.length - 1 && changed;
          return st === undefined ? (
            <i key={d} className="th-dot is-none" title={`${dayLabel(d)}: no reading`} />
          ) : (
            <i key={d} className={`th-dot is-${st.replace(" ", "-")}${isNow ? " is-changed" : ""}`} title={`${dayLabel(d)}: ${STATUS_WORD[st]}`} />
          );
        })}
      </span>
      <span className={changed ? "th-ind-now is-changed" : "th-ind-now"}>
        {STATUS_WORD[now.status]}
        {changed && prev && <span className="th-ind-was"> (was {STATUS_WORD[prev.status]})</span>}
      </span>
    </li>
  );
}

function Indicators({ rows }: { rows: IndicatorRow[] }) {
  if (rows.length === 0) return null;
  const all = Array.from(new Set(rows.flatMap((r) => r.history.map((h) => isoDay(h.date))).filter(Boolean))).sort();
  const days = all.slice(-STRIP_DAYS);
  const sorted = [...rows].sort((a, b) => RANK[b.history[b.history.length - 1].status] - RANK[a.history[a.history.length - 1].status]);
  const shown = sorted.slice(0, INDICATORS_SHOWN);
  const rest = sorted.slice(INDICATORS_SHOWN);
  const vars = { "--n": Math.max(1, days.length) } as CSSProperties;
  return (
    <div className="th-inds">
      <p className="th-sub">
        Signals we are watching for <span className="th-key"><i className="th-dot is-not-seen" /> not seen <i className="th-dot is-emerging" /> emerging <i className="th-dot is-observed" /> observed</span>
      </p>
      <ul className="th-ind-list" style={vars}>
        {days.length > 1 && (
          <li className="th-ind th-ind-axis" aria-hidden="true">
            <span />
            <span className="th-ind-ends">
              <span>{dayLabel(days[0])}</span>
              <span>{dayLabel(days[days.length - 1])}</span>
            </span>
            <span />
          </li>
        )}
        {shown.map((r) => (
          <IndicatorLine key={r.signal} row={r} days={days} />
        ))}
      </ul>
      {rest.length > 0 && (
        <Overflow label={`All signals (${sorted.length})`} trigger={`${rest.length} more signal${rest.length === 1 ? "" : "s"}`} wide>
          <ul className="th-ind-list" style={vars}>
            {rest.map((r) => (
              <IndicatorLine key={r.signal} row={r} days={days} />
            ))}
          </ul>
        </Overflow>
      )}
    </div>
  );
}

// ---- the way out ------------------------------------------------------------------------------
function Elsewhere({ d, known }: { d: Dossier; known: Set<string> }) {
  if (d.links.length === 0 && d.reports.length === 0 && d.briefs.length === 0) return null;
  const reports = [...d.reports].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
  const briefs = [...d.briefs].sort((a, b) => (a.as_of < b.as_of ? 1 : a.as_of > b.as_of ? -1 : 0));
  return (
    <div className="th-out">
      {d.links.length > 0 && (
        <div>
          <p className="th-sub">Linked theaters</p>
          <ul className="th-links">
            {d.links.slice(0, 5).map((l, i) => (
              <li key={i}>
                {known.has(l.theater_id) ? <Anchor url={`/intel/theaters/${l.theater_id}`}>{l.name || l.theater_id}</Anchor> : <b>{l.name || l.theater_id}</b>}
                {l.link && <span className="geo-muted"> {claimOf(l.link, 120)}</span>}
                {l.date && <span className="th-when"> {dayLabel(isoDay(l.date) || l.date)}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {reports.length > 0 && (
        <div>
          <p className="th-sub">Daily reports that covered it</p>
          <p className="th-chips">
            {reports.slice(0, 8).map((r, i) => (
              <Anchor key={i} url={r.url} className="th-chip-link">
                {dayLabel(isoDay(r.date) || r.date)}
              </Anchor>
            ))}
            {reports.length > 8 && (
              <Overflow label={`All reports (${reports.length})`} trigger={`${reports.length - 8} earlier`}>
                <p className="th-chips">
                  {reports.slice(8).map((r, i) => (
                    <Anchor key={i} url={r.url} className="th-chip-link">
                      {dayLabel(isoDay(r.date) || r.date)}
                    </Anchor>
                  ))}
                </p>
              </Overflow>
            )}
          </p>
        </div>
      )}
      {briefs.length > 0 && (
        <div>
          <p className="th-sub">Deep briefs</p>
          <ul className="th-links">
            {briefs.slice(0, 4).map((b, i) => (
              <li key={i}>
                <Anchor url={b.url || `/intel/briefs/${b.slug}`}>{b.title}</Anchor>
                {b.as_of && <span className="th-when"> {dayLabel(isoDay(b.as_of) || b.as_of)}</span>}
              </li>
            ))}
          </ul>
          {briefs.length > 4 && (
            <Overflow label={`All briefs (${briefs.length})`} trigger={`${briefs.length - 4} more`}>
              <ul className="th-links">
                {briefs.slice(4).map((b, i) => (
                  <li key={i}>
                    <Anchor url={b.url || `/intel/briefs/${b.slug}`}>{b.title}</Anchor>
                    {b.as_of && <span className="th-when"> {dayLabel(isoDay(b.as_of) || b.as_of)}</span>}
                  </li>
                ))}
              </ul>
            </Overflow>
          )}
        </div>
      )}
    </div>
  );
}

export default function DossierOutlook({ d, known }: { d: Dossier; known: Set<string> }) {
  const open = d.forecasts.filter((f) => f.status === "open").sort((a, b) => b.probability - a.probability);
  const resolved = d.forecasts.filter((f) => f.status !== "open");
  if (open.length === 0 && resolved.length === 0 && d.indicators.length === 0 && d.links.length === 0 && d.reports.length === 0 && d.briefs.length === 0) return null;
  const lead = open.length > 0 ? `Most likely next: ${claimOf(open[0].statement, 130)} (${open[0].probability}%)` : resolved.length > 0 ? `${resolved.length} forecast${resolved.length === 1 ? "" : "s"} resolved; none open.` : undefined;
  return (
    <Section id="heading" title="Where it's heading" lead={lead}>
      {open.length > 0 && (
        <div className="th-fcs">
          <p className="th-sub">
            Open forecasts <span className="th-key">probability, on a 0 to 100 scale</span>
          </p>
          <ul className="th-fc-list">
            {open.slice(0, FORECASTS_SHOWN).map((f) => (
              <OpenRow key={f.id} f={f} />
            ))}
          </ul>
          {open.length > FORECASTS_SHOWN && (
            <Overflow label={`All open forecasts (${open.length})`} trigger={`${open.length - FORECASTS_SHOWN} more forecast${open.length - FORECASTS_SHOWN === 1 ? "" : "s"}`} wide>
              <ul className="th-fc-list">
                {open.slice(FORECASTS_SHOWN).map((f) => (
                  <OpenRow key={f.id} f={f} />
                ))}
              </ul>
            </Overflow>
          )}
        </div>
      )}
      {resolved.length > 0 && (
        <div className="th-fcs">
          <p className="th-sub">Already settled</p>
          <ul className="th-res-list">
            {resolved.slice(0, RESOLVED_SHOWN).map((f) => (
              <ResolvedRow key={f.id} f={f} />
            ))}
          </ul>
          {resolved.length > RESOLVED_SHOWN && (
            <Overflow label={`All settled forecasts (${resolved.length})`} trigger={`${resolved.length - RESOLVED_SHOWN} more`} wide>
              <ul className="th-res-list">
                {resolved.slice(RESOLVED_SHOWN).map((f) => (
                  <ResolvedRow key={f.id} f={f} />
                ))}
              </ul>
            </Overflow>
          )}
        </div>
      )}
      <Indicators rows={d.indicators} />
      <Elsewhere d={d} known={known} />
    </Section>
  );
}
