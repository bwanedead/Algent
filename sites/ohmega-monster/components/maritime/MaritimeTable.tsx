"use client";

import { Fragment, useMemo, useState } from "react";

import IsoFlags from "@/components/IsoFlags";
import { countryName } from "@/lib/flags";
import {
  confidenceWord, flagsOf, kindLabel, KIND_COLOR, KIND_LABEL, KIND_ORDER, pct, tally, vesselLabel, type MaritimeEvent, type MaritimeKind,
} from "@/lib/maritime-shared";

import EventDetail from "./EventDetail";

import "./maritime.css";

// /intel/maritime: counts per kind, per flag state and per area (each a filter) over a dense table of behaviour events with the same filters as
// selects; a row opens into its full detail (why flagged, identity, mini track, evidence). Rows and the clock come from the server page; this file
// imports only the pure shared file (no server-only modules).

const PAGE = 60;

export default function MaritimeTable({ rows, nowMs }: { rows: MaritimeEvent[]; nowMs: number }) {
  const [kind, setKind] = useState<MaritimeKind | "">("");
  const [flag, setFlag] = useState("");
  const [area, setArea] = useState("");
  const [state, setState] = useState<"" | "ongoing" | "ended">("");
  const [open, setOpen] = useState<string | null>(null);
  const [limit, setLimit] = useState(PAGE);

  const reset = () => setLimit(PAGE);
  const shown = useMemo(
    () => rows.filter((e) => (!kind || e.kind === kind) && (!flag || flagsOf(e).includes(flag)) && (!area || e.area === area) && (!state || (state === "ongoing") === (e.ended_at === null))),
    [rows, kind, flag, area, state],
  );
  const byKind = useMemo(() => tally(rows, (e) => e.kind), [rows]);
  const byFlag = useMemo(() => tally(rows, flagsOf), [rows]);
  const byArea = useMemo(() => tally(rows, (e) => e.area), [rows]);
  const nOpenArea = rows.filter((e) => !e.area).length;

  return (
    <div className="mb-view">
      <div>
        <p className="mb-group">By kind</p>
        <ul className="mb-counts" aria-label="Events by kind">
          {KIND_ORDER.map((k) => (
            <li key={k}>
              <button type="button" className={`mb-count${kind === k ? " is-on" : ""}`} aria-pressed={kind === k} onClick={() => { setKind(kind === k ? "" : k); reset(); }}>
                <span><span className="mb-dot" style={{ background: KIND_COLOR[k] }} aria-hidden="true" />{KIND_LABEL[k]}</span>
                <span className="mb-count-n">{byKind.find((c) => c.key === k)?.n ?? 0}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p className="mb-group">By flag state (the registry of the radio identity; flags of convenience show as such)</p>
        <ul className="mb-counts" aria-label="Events by flag state">
          {byFlag.slice(0, 12).map((c) => (
            <li key={c.key}>
              <button type="button" className={`mb-count${flag === c.key ? " is-on" : ""}`} aria-pressed={flag === c.key} onClick={() => { setFlag(flag === c.key ? "" : c.key); reset(); }}>
                <span><IsoFlags codes={[c.key]} /> {countryName(c.key)}</span>
                <span className="mb-count-n">{c.n}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p className="mb-group">By area</p>
        <ul className="mb-counts" aria-label="Events by area">
          {byArea.slice(0, 12).map((c) => (
            <li key={c.key}>
              <button type="button" className={`mb-count${area === c.key ? " is-on" : ""}`} aria-pressed={area === c.key} onClick={() => { setArea(area === c.key ? "" : c.key); reset(); }}>
                <span>{c.key}</span>
                <span className="mb-count-n">{c.n}</span>
              </button>
            </li>
          ))}
          {nOpenArea > 0 && (
            <li>
              <span className="mb-count" aria-label={`${nOpenArea} events outside every named area`}>
                <span>Open ocean, no named area</span>
                <span className="mb-count-n">{nOpenArea}</span>
              </span>
            </li>
          )}
        </ul>
      </div>

      <div className="mb-filters" role="group" aria-label="Filter the events">
        <label>
          <span className="vl-label">Kind</span>
          <select value={kind} onChange={(e) => { setKind(e.target.value as MaritimeKind | ""); reset(); }}>
            <option value="">All kinds</option>
            {KIND_ORDER.map((k) => (
              <option key={k} value={k}>{KIND_LABEL[k]}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="vl-label">Flag state</span>
          <select value={flag} onChange={(e) => { setFlag(e.target.value); reset(); }}>
            <option value="">All flags</option>
            {byFlag.map((c) => (
              <option key={c.key} value={c.key}>{countryName(c.key)} ({c.n})</option>
            ))}
          </select>
        </label>
        <label>
          <span className="vl-label">Area</span>
          <select value={area} onChange={(e) => { setArea(e.target.value); reset(); }}>
            <option value="">All areas</option>
            {byArea.map((c) => (
              <option key={c.key} value={c.key}>{c.key} ({c.n})</option>
            ))}
          </select>
        </label>
        <label>
          <span className="vl-label">State</span>
          <select value={state} onChange={(e) => { setState(e.target.value as "" | "ongoing" | "ended"); reset(); }}>
            <option value="">Ongoing and ended</option>
            <option value="ongoing">Ongoing</option>
            <option value="ended">Ended</option>
          </select>
        </label>
        <p className="mb-total">{shown.length} {shown.length === 1 ? "event" : "events"}</p>
      </div>

      {shown.length === 0 ? (
        <p className="mb-empty">Nothing matches.</p>
      ) : (
        <div className="mb-scroll">
          <table className="mb-table">
            <thead>
              <tr>
                <th scope="col">Since (UTC)</th>
                <th scope="col">Kind</th>
                <th scope="col">Vessel</th>
                <th scope="col">Flag</th>
                <th scope="col">Area</th>
                <th scope="col">Confidence</th>
                <th scope="col" aria-label="Detail" />
              </tr>
            </thead>
            <tbody>
              {shown.slice(0, limit).map((e) => (
                <Fragment key={e.id}>
                  <tr className={open === e.id ? "mb-open" : undefined}>
                    <td className="mb-when">{e.started_at.slice(0, 16).replace("T", " ")}{e.ended_at === null && <span className="mb-sub">ongoing</span>}</td>
                    <td><span className="mb-dot" style={{ background: KIND_COLOR[e.kind] }} aria-hidden="true" />{kindLabel(e.kind)}</td>
                    <td className="mb-name">
                      {vesselLabel(e)}
                      <span className="mb-sub">{[e.imo ? `IMO ${e.imo}` : "", `MMSI ${e.mmsi}`, e.ship_class].filter(Boolean).join(" · ")}</span>
                    </td>
                    <td><IsoFlags codes={flagsOf(e)} /></td>
                    <td className="mb-area">{e.area || "open ocean"}</td>
                    <td className="mb-conf">{pct(e.confidence)} <span className="mb-sub">{confidenceWord(e.confidence)}</span></td>
                    <td>
                      <button type="button" className="mb-expand" aria-expanded={open === e.id} onClick={() => setOpen(open === e.id ? null : e.id)}>
                        {open === e.id ? "Hide" : "Why"}
                      </button>
                    </td>
                  </tr>
                  {open === e.id && (
                    <tr className="mb-open">
                      <td colSpan={7} className="mb-detail-cell">
                        <EventDetail e={e} nowMs={nowMs} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {shown.length > limit && (
        <button type="button" className="mb-more" onClick={() => setLimit(limit + PAGE)}>
          Show {Math.min(PAGE, shown.length - limit)} more
        </button>
      )}
    </div>
  );
}
