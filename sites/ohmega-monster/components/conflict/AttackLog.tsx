"use client";

import { useMemo, useState } from "react";

import IsoFlags from "@/components/IsoFlags";
import { Spark } from "@/components/vl/primitives";
import { byCountry, dailyCounts, EVENT_SOURCES, EVENT_TYPES, logProvenance, typeLabel, type ConflictRow, type EventSource, type EventType } from "@/lib/conflict-shared";
import { countryName } from "@/lib/flags";

import Provenance from "./Provenance";
import "./conflict.css";

// /intel/attacks: a per-country strip over a dense table of events, filterable by country, kind of event, source and confidence. Rows
// come from the server page; this file imports only the pure shared file. Every row says which source reported it and how it was
// coded (machine-coded GDELT rows are marked and can be hidden); the figures at the top carry their provenance in an info hover.

const PAGE = 60;

export default function AttackLog({ rows, today, since }: { rows: ConflictRow[]; today: string; since: string | null }) {
  const [country, setCountry] = useState("");
  const [type, setType] = useState<EventType | "">("");
  const [source, setSource] = useState<EventSource | "">("");
  const [sure, setSure] = useState(false);
  const [limit, setLimit] = useState(PAGE);

  const shown = useMemo(
    () => rows.filter((r) => (!country || r.country === country) && (!type || r.type === type) && (!source || r.source === source) && (!sure || r.confidence !== "low")),
    [rows, country, type, source, sure],
  );
  const countries = useMemo(() => byCountry(rows).filter((c) => c.iso !== ""), [rows]);
  const sources = useMemo(() => Array.from(new Set(rows.map((r) => r.source))), [rows]);
  const prov = useMemo(() => logProvenance(rows, since), [rows, since]);
  const reset = () => setLimit(PAGE);

  return (
    <div className="cx-view">
      <p className="cx-headline">
        <strong>{rows.length}</strong> {rows.length === 1 ? "event" : "events"} reported in the last 14 days across <strong>{countries.length}</strong> countries <Provenance p={prov} label="the event count" />
      </p>

      <ul className="cx-countries" aria-label="Events by country, last 14 days">
        {countries.slice(0, 12).map((c) => (
          <li key={c.iso}>
            <button type="button" className={`cx-country${country === c.iso ? " is-on" : ""}`} aria-pressed={country === c.iso} onClick={() => { setCountry(country === c.iso ? "" : c.iso); reset(); }}>
              <IsoFlags codes={[c.iso]} />
              <span className="cx-country-n">{countryName(c.iso)}</span>
              <span className="cx-country-c">{c.n}</span>
              <Spark values={dailyCounts(rows.filter((r) => r.country === c.iso), today, 14)} label={`${countryName(c.iso)}: events per day, last 14 days`} />
            </button>
          </li>
        ))}
      </ul>

      <div className="cx-filters" role="group" aria-label="Filter the events">
        <label>
          <span className="vl-label">Country</span>
          <select value={country} onChange={(e) => { setCountry(e.target.value); reset(); }}>
            <option value="">All countries</option>
            {countries.map((c) => (
              <option key={c.iso} value={c.iso}>{countryName(c.iso)}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="vl-label">Kind</span>
          <select value={type} onChange={(e) => { setType(e.target.value as EventType | ""); reset(); }}>
            <option value="">All kinds</option>
            {EVENT_TYPES.map((t) => (
              <option key={t.id} value={t.id}>{t.label}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="vl-label">Source</span>
          <select value={source} onChange={(e) => { setSource(e.target.value as EventSource | ""); reset(); }}>
            <option value="">All sources</option>
            {sources.map((s) => (
              <option key={s} value={s}>{EVENT_SOURCES[s]?.name ?? s}</option>
            ))}
          </select>
        </label>
        <label className="cx-check">
          <input type="checkbox" checked={sure} onChange={(e) => { setSure(e.target.checked); reset(); }} />
          <span>Hide single-source, low-confidence rows</span>
        </label>
        <p className="cx-count">{shown.length} {shown.length === 1 ? "event" : "events"}</p>
      </div>

      {shown.length === 0 ? (
        <p className="cx-empty">Nothing matches.</p>
      ) : (
        <div className="cx-scroll">
          <table className="cx-table cx-table-log">
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Kind</th>
                <th scope="col">Place</th>
                <th scope="col">Parties</th>
                <th scope="col" title="Fatalities as the source states them. Blank: the source does not say (GDELT never does).">Killed</th>
                <th scope="col" title="Articles or reports behind the event">Reports</th>
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              {shown.slice(0, limit).map((r) => (
                <tr key={r.id}>
                  <td className="cx-date">{r.on_date}</td>
                  <td>{typeLabel(r.type)}</td>
                  <td className="cx-place">
                    {r.country && <IsoFlags codes={[r.country]} />} {r.place || r.title}
                    {r.assets.length > 0 && (
                      <span className="cx-sub" title="Places in Ohmega's ledger within a few kilometres of the event. Nearby is not the same as hit.">
                        {" "}near {r.assets.map((a) => a.name).join(", ")}
                      </span>
                    )}
                  </td>
                  <td className="cx-parties">{[r.actor1, r.actor2].filter(Boolean).join(" / ")}</td>
                  <td className="cx-num">{r.fatalities ?? ""}</td>
                  <td className="cx-num">{r.articles}</td>
                  <td>
                    {r.urls[0] ? (
                      <a href={r.urls[0]} className="xt" rel="noopener noreferrer" title={r.coverage_note}>{EVENT_SOURCES[r.source]?.short ?? r.source} ↗</a>
                    ) : (
                      <span title={r.coverage_note}>{EVENT_SOURCES[r.source]?.short ?? r.source}</span>
                    )}
                    {r.coding === "machine" && <span className="cx-sub cx-machine" title={r.coverage_note}> machine-coded</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {shown.length > limit && (
        <button type="button" className="cx-more" onClick={() => setLimit(limit + PAGE)}>
          Show {Math.min(PAGE, shown.length - limit)} more
        </button>
      )}
    </div>
  );
}
