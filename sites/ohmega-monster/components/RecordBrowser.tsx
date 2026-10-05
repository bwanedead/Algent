"use client";

import { useMemo, useState } from "react";

import { NO_FILTER, applyFilter, signalLabel, tally, type OnRecord, type RecordFilter } from "@/lib/record-model";

import { RecordRow } from "./OnRecord";
import "./record.css";

const SHOWN = 60;

function Select({ label, value, options, onChange }: { label: string; value: string; options: { value: string; n: number }[]; onChange: (v: string) => void }) {
  return (
    <label>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.value} ({o.n})
          </option>
        ))}
      </select>
    </label>
  );
}

/** Filterable list of statements. `fields` picks which filters to offer (the dossier only needs the speaker). */
export default function RecordBrowser({ rows, fields = ["speaker", "by", "about", "signal", "date"] }: { rows: OnRecord[]; fields?: string[] }) {
  const [f, setF] = useState<RecordFilter>(NO_FILTER);
  const [all, setAll] = useState(false);
  const set = (k: keyof RecordFilter) => (v: string) => setF((p) => ({ ...p, [k]: v }));
  const speakers = useMemo(() => tally(rows.map((r) => r.speaker)), [rows]);
  const bys = useMemo(() => tally(rows.map((r) => r.affiliation)), [rows]);
  const abouts = useMemo(() => tally(rows.flatMap((r) => r.about)).slice(0, 80), [rows]);
  const signals = useMemo(() => tally(rows.map((r) => r.signal)).map((o) => ({ ...o, value: o.value })), [rows]);
  const shown = useMemo(() => applyFilter(rows, f), [rows, f]);
  const list = all ? shown : shown.slice(0, SHOWN);
  const has = (k: string) => fields.includes(k);
  return (
    <div>
      <div className="rec-filters" role="group" aria-label="Filter the record">
        {has("speaker") && <Select label="Speaker" value={f.speaker} options={speakers} onChange={set("speaker")} />}
        {has("by") && <Select label="Speaking for" value={f.by} options={bys} onChange={set("by")} />}
        {has("about") && <Select label="About" value={f.about} options={abouts} onChange={set("about")} />}
        {has("signal") && (
          <label>
            Kind
            <select value={f.signal} onChange={(e) => set("signal")(e.target.value)}>
              <option value="">All</option>
              {signals.map((o) => (
                <option key={o.value} value={o.value}>
                  {signalLabel(o.value)} ({o.n})
                </option>
              ))}
            </select>
          </label>
        )}
        {has("date") && (
          <>
            <label>
              From
              <input type="date" value={f.from} onChange={(e) => set("from")(e.target.value)} />
            </label>
            <label>
              To
              <input type="date" value={f.to} onChange={(e) => set("to")(e.target.value)} />
            </label>
          </>
        )}
      </div>
      <p className="rec-count">
        {shown.length} statement{shown.length === 1 ? "" : "s"}, newest first
      </p>
      <ul className="rec-list">
        {list.map((r) => (
          <RecordRow key={r.id} r={r} />
        ))}
      </ul>
      {!all && shown.length > SHOWN && (
        <button type="button" className="geo-link-btn" onClick={() => setAll(true)}>
          Show all {shown.length} ›
        </button>
      )}
    </div>
  );
}
