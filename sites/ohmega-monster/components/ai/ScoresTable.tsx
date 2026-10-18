"use client";

import { useMemo, useState } from "react";

import "./ai.css";

// The latest-scores table: one row per benchmark (its current leader), sortable. Plain rows come from the server page (already formatted); sort keys are
// numbers carried alongside so "85%" and "9.2 h" sort by value, not by text. Client-safe: imports nothing server-only.

export type ScoreRow = {
  id: string;
  name: string;
  url: string;
  best: string;
  model: string;
  lab: string;
  labName: string;
  labColor: string;
  weights: string;
  models: number;
  saturation: number | null;
  year: string;
  yearSort: number | null;
  asOf: string; // ISO date, the sort key
  asOfLabel: string;
  stale: boolean;
};

type Key = "name" | "models" | "saturation" | "yearSort" | "asOf";
const COLS: { key: Key | null; label: string; num?: boolean }[] = [
  { key: "name", label: "Benchmark" },
  { key: null, label: "Leader" },
  { key: null, label: "Lab" },
  { key: null, label: "Weights" },
  { key: "models", label: "Models", num: true },
  { key: "saturation", label: "Of ceiling", num: true },
  { key: "yearSort", label: "12 months", num: true },
  { key: "asOf", label: "As of" },
];

export default function ScoresTable({ rows }: { rows: ScoreRow[] }) {
  const [key, setKey] = useState<Key>("models");
  const [dir, setDir] = useState<1 | -1>(-1);
  const sorted = useMemo(() => {
    const num = (r: ScoreRow): number => {
      const x = key === "models" ? r.models : key === "saturation" ? r.saturation : r.yearSort;
      return x === null ? (dir === 1 ? Infinity : -Infinity) : x;
    };
    return [...rows].sort((a, b) => {
      const c = key === "name" ? a.name.localeCompare(b.name) : key === "asOf" ? a.asOf.localeCompare(b.asOf) : Math.sign(num(a) - num(b));
      return (c || a.name.localeCompare(b.name)) * dir;
    });
  }, [rows, key, dir]);
  const click = (k: Key | null) => {
    if (!k) return;
    if (k === key) setDir(dir === 1 ? -1 : 1);
    else {
      setKey(k);
      setDir(k === "name" ? 1 : -1);
    }
  };
  return (
    <div className="ai-scroll">
      <table className="ai-table">
        <thead>
          <tr>
            {COLS.map((c) => (
              <th key={c.label} className={c.num ? "n" : undefined} aria-sort={c.key && c.key === key ? (dir === 1 ? "ascending" : "descending") : undefined}>
                {c.key ? (
                  <button type="button" className="ai-sort" onClick={() => click(c.key)}>
                    {c.label}
                    {c.key === key ? (dir === 1 ? " ↑" : " ↓") : ""}
                  </button>
                ) : (
                  c.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.id}>
              <td className="ai-name">
                <a href={r.url || undefined}>{r.name}</a>
                <span className="ai-best">{r.best}</span>
              </td>
              <td>{r.model}</td>
              <td>
                <span className="ai-chip" style={{ background: r.labColor }} aria-hidden="true" /> {r.labName}
              </td>
              <td className={r.weights === "open" ? "ai-open" : undefined}>{r.weights || "n/a"}</td>
              <td className="n">{r.models}</td>
              <td className="n">{r.saturation === null ? "n/a" : `${Math.round(r.saturation * 100)}%`}</td>
              <td className="n">{r.year}</td>
              <td className={`ai-date${r.stale ? " is-stale" : ""}`}>{r.asOfLabel}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
