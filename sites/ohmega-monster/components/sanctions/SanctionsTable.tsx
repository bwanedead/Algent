"use client";

import { useMemo, useState } from "react";

import IsoFlags from "@/components/IsoFlags";
import { Spark } from "@/components/vl/primitives";
import { countryName } from "@/lib/flags";
import { byCountry, SOURCES, TYPES, typeLabel, type SanctionsAction, type SanctionsRow, type SanctionsSource, type SanctionsType } from "@/lib/sanctions-shared";

import "./sanctions.css";

// /intel/sanctions: a per-country strip (designations in the last 30 days with a sparkline) over a dense table of events, filterable by
// list, kind of party, action and country. Plain rows and today's date come from the server page; this file imports only the pure
// shared file (no server-only modules). Every row links to the list it came from.

const PAGE = 60;

export default function SanctionsTable({ rows, today }: { rows: SanctionsRow[]; today: string }) {
  const [source, setSource] = useState<SanctionsSource | "">("");
  const [type, setType] = useState<SanctionsType | "">("");
  const [action, setAction] = useState<SanctionsAction | "">("");
  const [country, setCountry] = useState("");
  const [limit, setLimit] = useState(PAGE);

  const shown = useMemo(
    () => rows.filter((r) => (!source || r.source === source) && (!type || r.type === type) && (!action || r.action === action) && (!country || r.countries.includes(country))),
    [rows, source, type, action, country],
  );
  const countries = useMemo(() => byCountry(rows, today, 30), [rows, today]);
  const top = countries.slice(0, 12);
  const reset = () => setLimit(PAGE);

  return (
    <div className="sx-view">
      <ul className="sx-countries" aria-label="Designations by country, last 30 days">
        {top.map((c) => (
          <li key={c.iso}>
            <button type="button" className={`sx-country${country === c.iso ? " is-on" : ""}`} aria-pressed={country === c.iso} onClick={() => { setCountry(country === c.iso ? "" : c.iso); reset(); }}>
              <IsoFlags codes={[c.iso]} />
              <span className="sx-country-n">{countryName(c.iso)}</span>
              <span className="sx-country-c">{c.designated}</span>
              <Spark values={c.spark} label={`${countryName(c.iso)}: designations per day, last 30 days`} />
            </button>
          </li>
        ))}
      </ul>

      <div className="sx-filters" role="group" aria-label="Filter the designations">
        <label>
          <span className="vl-label">List</span>
          <select value={source} onChange={(e) => { setSource(e.target.value as SanctionsSource | ""); reset(); }}>
            <option value="">All lists</option>
            {(Object.keys(SOURCES) as SanctionsSource[]).map((s) => (
              <option key={s} value={s}>{SOURCES[s].name}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="vl-label">Kind</span>
          <select value={type} onChange={(e) => { setType(e.target.value as SanctionsType | ""); reset(); }}>
            <option value="">All kinds</option>
            {TYPES.map((t) => (
              <option key={t.id} value={t.id}>{t.label}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="vl-label">Action</span>
          <select value={action} onChange={(e) => { setAction(e.target.value as SanctionsAction | ""); reset(); }}>
            <option value="">Added and removed</option>
            <option value="designated">Added (designated)</option>
            <option value="delisted">Removed (delisted)</option>
          </select>
        </label>
        <label>
          <span className="vl-label">Country</span>
          <select value={country} onChange={(e) => { setCountry(e.target.value); reset(); }}>
            <option value="">All countries</option>
            {countries.map((c) => (
              <option key={c.iso} value={c.iso}>{countryName(c.iso)}</option>
            ))}
          </select>
        </label>
        <p className="sx-count">{shown.length} {shown.length === 1 ? "event" : "events"}</p>
      </div>

      {shown.length === 0 ? (
        <p className="sx-empty">Nothing matches.</p>
      ) : (
        <div className="sx-scroll">
          <table className="sx-table">
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Action</th>
                <th scope="col">Name</th>
                <th scope="col">Kind</th>
                <th scope="col">Countries</th>
                <th scope="col">Programme</th>
                <th scope="col">List</th>
              </tr>
            </thead>
            <tbody>
              {shown.slice(0, limit).map((r) => (
                <tr key={r.id} className={r.action === "delisted" ? "is-removed" : undefined}>
                  <td className="sx-date">{r.on_date}</td>
                  <td>
                    <span className={`sx-act sx-act-${r.action}`}>{r.action === "designated" ? "Added" : "Removed"}</span>
                  </td>
                  <td className="sx-name">
                    {r.name}
                    {r.type === "vessel" && r.imo && <span className="sx-sub"> IMO {r.imo}{r.owner ? ` · ${r.owner}` : ""}</span>}
                  </td>
                  <td>{typeLabel(r.type)}</td>
                  <td>
                    <IsoFlags codes={r.countries.slice(0, 4)} />
                  </td>
                  <td className="sx-prog">{r.programmes.slice(0, 2).join(", ")}</td>
                  <td>
                    <a href={r.source_url} className="xt" rel="noopener noreferrer" title={SOURCES[r.source].name}>
                      {SOURCES[r.source].short} ↗
                    </a>
                    {r.baseline && <span className="sx-sub" title="Found when we first read this list: the list dates it itself"> listed date</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {shown.length > limit && (
        <button type="button" className="sx-more" onClick={() => setLimit(limit + PAGE)}>
          Show {Math.min(PAGE, shown.length - limit)} more
        </button>
      )}
    </div>
  );
}
