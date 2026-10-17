"use client";

// The globe's side panel: a theater (name, countries, link) or a country (its full brief history, then real supplemental stats
// fetched lazily from /api/globe/country/[iso]: the briefs newest first with theme-coloured dots, stat rows with a tiny bar against the world median, and counts of what is going on).

import Link from "next/link";
import { useEffect, useState } from "react";

import IsoFlags from "@/components/IsoFlags";
import { DirTick } from "@/components/vl/primitives";
import type { Countries } from "@/lib/globe/countries";
import type { CountryBrief, CountryHeadline, CountryPanel, GlobeData } from "@/lib/globe/data";
import { THEMES } from "@/lib/globe/themes";

export type Pick = { kind: "country"; iso: string } | { kind: "theater"; id: string };

const COUNTS: { key: keyof CountryPanel["counts"]; one: string; many: string }[] = [
  { key: "theaters", one: "theater involved", many: "theaters involved" },
  { key: "statements7d", one: "statement this week", many: "statements this week" },
  { key: "sanctions30d", one: "sanctions event, 30 days", many: "sanctions events, 30 days" },
  { key: "calendar", one: "item ahead on the calendar", many: "items ahead on the calendar" },
  { key: "anomalies", one: "live anomaly", many: "live anomalies" },
];

function useCountryPanel(iso: string): CountryPanel | "loading" | null {
  const [state, setState] = useState<{ iso: string; panel: CountryPanel | null } | null>(null);
  useEffect(() => {
    let dead = false;
    fetch(`/api/globe/country/${iso}`)
      .then((r) => (r.ok ? (r.json() as Promise<CountryPanel>) : null))
      .catch(() => null)
      .then((panel) => { if (!dead) setState({ iso, panel }); });
    return () => { dead = true; };
  }, [iso]);
  return state && state.iso === iso ? state.panel : "loading";
}

const BRIEF_PAGE = 40; // rows revealed per press of "More"
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dayLabel = (date: string): string => `${Number(date.slice(8, 10))} ${MONTHS[Number(date.slice(5, 7)) - 1] ?? ""} ${date.slice(0, 4)}`;
const themeLabel = (id: CountryBrief["theme"]): string => THEMES.find((t) => t.id === id)?.label ?? id;

/** Every brief naming the country, newest first, grouped by day. The dot's colour is the legend's theme colour (the same CSS classes). */
function Briefs({ briefs }: { briefs: CountryBrief[] }) {
  const [shown, setShown] = useState(BRIEF_PAGE);
  const rows = briefs.slice(0, shown);
  return (
    <>
      <p className="gv-panel-sub gv-panel-sub-first">Briefs ({briefs.length})</p>
      <div className="gv-briefs" tabIndex={0} aria-label="Briefs naming this country">
        <ul>
          {rows.map((b, i) => (
            <li key={`${b.href}-${i}`}>
              {(i === 0 || rows[i - 1].date !== b.date) && <span className="gv-brief-day">{dayLabel(b.date)}</span>}
              <Link href={b.href} className="gv-brief">
                <span className={`gv-bd gv-th gv-t-${b.theme} gv-r0`} role="img" aria-label={themeLabel(b.theme)} title={themeLabel(b.theme)} />
                <span className="gv-brief-text">{b.text}</span>
              </Link>
            </li>
          ))}
        </ul>
        {shown < briefs.length && <button type="button" className="gv-more" onClick={() => setShown((n) => n + BRIEF_PAGE)}>More ({briefs.length - shown})</button>}
      </div>
    </>
  );
}

function CountryBody({ iso, fallback }: { iso: string; fallback: CountryHeadline | null }) {
  const p = useCountryPanel(iso);
  if (p === "loading") {
    return (
      <>
        {fallback && <p className="gv-panel-head"><Link href={fallback.href} className="xt">{fallback.text}</Link><span className="gv-panel-date"> {fallback.date}</span></p>}
        <p className="gv-panel-none">Loading briefs and figures...</p>
      </>
    );
  }
  if (!p) return null;
  return (
    <>
      {p.briefs.length > 0 ? <Briefs briefs={p.briefs} /> : <p className="gv-panel-none">Not named in the daily reports.</p>}
      {p.leaders.head_of_state && <p className="gv-panel-lead">{p.leaders.head_of_state}{p.leaders.head_of_government && p.leaders.head_of_government !== p.leaders.head_of_state ? ` · ${p.leaders.head_of_government}` : ""}</p>}
      <ul className="gv-counts">
        {COUNTS.filter((c) => p.counts[c.key] > 0).map((c) => (
          <li key={c.key}><b>{p.counts[c.key]}</b> {p.counts[c.key] === 1 ? c.one : c.many}</li>
        ))}
      </ul>
      {p.grid && <p className="gv-panel-grid"><span className="gv-panel-sub-inline">Grid impact</span> {p.grid.line}</p>}
      {p.stats.length > 0 && (
        <>
          <p className="gv-panel-sub">Against the world median</p>
          <ul className="gv-stats">
            {p.stats.map((s) => (
              <li key={s.id} title={s.median ? `World median ${s.median} (${s.year} figure)` : `${s.year} figure`}>
                <span className="gv-stat-k">{s.label}</span>
                <span className="gv-stat-v">{s.text}</span>
                {s.pos !== null && <span className="gv-stat-bar" aria-hidden="true"><i style={{ width: `${Math.round(s.pos * 100)}%` }} /></span>}
              </li>
            ))}
          </ul>
          <p className="gv-panel-fine">Bar: log scale, the tick is the world median, a factor of ten either side spans it.</p>
        </>
      )}
    </>
  );
}

export default function GlobePanel({ pick, data, geo, onClose }: { pick: Pick; data: GlobeData; geo: Countries | null; onClose: () => void }) {
  if (pick.kind === "theater") {
    const t = data.theaters.find((x) => x.id === pick.id);
    if (!t) return null;
    return (
      <aside className="gv-panel" aria-label={t.name}>
        <button type="button" className="gv-close" onClick={onClose} aria-label="Close">&times;</button>
        <p className="gv-panel-kind">Theater</p>
        <h2 className="gv-panel-name"><DirTick direction={t.dir} /> {t.name}</h2>
        {t.iso.length > 0 && <p className="gv-panel-flags"><IsoFlags codes={t.iso} link /></p>}
        <p className="gv-panel-links"><Link href={t.href} className="xt">Latest report section ({t.date})</Link></p>
      </aside>
    );
  }
  const info = data.countries[pick.iso];
  const name = info?.name ?? geo?.list.find((c) => c.iso === pick.iso)?.name ?? pick.iso;
  return (
    <aside className="gv-panel" aria-label={name}>
      <button type="button" className="gv-close" onClick={onClose} aria-label="Close">&times;</button>
      <p className="gv-panel-kind">Country</p>
      <h2 className="gv-panel-name"><IsoFlags codes={[pick.iso]} /> {name}</h2>
      <CountryBody iso={pick.iso} fallback={info?.headline ?? null} />
      {info && info.theaters.length > 0 && (
        <>
          <p className="gv-panel-sub">Theaters</p>
          <ul className="gv-panel-list">
            {info.theaters.map((t) => (
              <li key={t.id}><DirTick direction={t.dir} /> {t.href ? <Link href={t.href} className="xt">{t.name}</Link> : t.name}</li>
            ))}
          </ul>
        </>
      )}
      {info?.page && <p className="gv-panel-links"><Link href={`/intel/actors/${pick.iso}`} className="xt">Country profile</Link></p>}
    </aside>
  );
}
