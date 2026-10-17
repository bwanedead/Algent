"use client";

// The globe's side panel: a theater (name, countries, link) or a country (newest headline, theaters, then real supplemental stats
// fetched lazily from /api/globe/country/[iso]: stat rows with a tiny bar against the world median, and counts of what is going on).

import Link from "next/link";
import { useEffect, useState } from "react";

import IsoFlags from "@/components/IsoFlags";
import { DirTick } from "@/components/vl/primitives";
import type { Countries } from "@/lib/globe/countries";
import type { CountryPanel, GlobeData } from "@/lib/globe/data";

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

function Stats({ iso }: { iso: string }) {
  const p = useCountryPanel(iso);
  if (p === "loading") return <p className="gv-panel-none">Loading figures...</p>;
  if (!p) return null;
  return (
    <>
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
      {info?.headline ? (
        <p className="gv-panel-head"><Link href={info.headline.href} className="xt">{info.headline.text}</Link><span className="gv-panel-date"> {info.headline.date}</span></p>
      ) : (
        <p className="gv-panel-none">Not named in the recent daily reports.</p>
      )}
      <Stats iso={pick.iso} />
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
