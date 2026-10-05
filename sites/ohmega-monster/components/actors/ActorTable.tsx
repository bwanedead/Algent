"use client";

import Link from "next/link";
import { useState } from "react";

import FlagRow from "@/components/FlagRow";
import { isoToFlagEmoji } from "@/lib/flags";

// The actors index as a sortable small-multiples table. The page hands over plain rows (value or null
// per metric); each column's bars share that column's one scale. Click a header to sort by it.

export type TableRow = { iso2: string; name: string; theaters: number; cells: Record<string, { value: number; text: string; year: number } | null> };
export type Column = { id: string; label: string };

export default function ActorTable({ rows, columns }: { rows: TableRow[]; columns: Column[] }) {
  const [key, setKey] = useState(columns[1]?.id ?? columns[0].id);
  const max: Record<string, number> = {};
  for (const c of columns) max[c.id] = Math.max(1, ...rows.map((r) => r.cells[c.id]?.value ?? 0));
  const sorted = [...rows].sort((a, b) => (b.cells[key]?.value ?? -1) - (a.cells[key]?.value ?? -1) || a.name.localeCompare(b.name));
  return (
    <div className="th-tbl-wrap">
      <table className="th-tbl ac-table">
        <thead>
          <tr>
            <th>Actor</th>
            {columns.map((c) => (
              <th key={c.id} aria-sort={c.id === key ? "descending" : "none"}>
                <button type="button" className={c.id === key ? "ac-sort is-on" : "ac-sort"} onClick={() => setKey(c.id)}>
                  {c.label}
                  {c.id === key ? " ▼" : ""}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.iso2}>
              <td>
                <Link href={`/intel/actors/${r.iso2}`} className="ac-row-name">
                  <FlagRow flags={[isoToFlagEmoji(r.iso2)]} places={[r.name]} className="ac-flag" /> {r.name}
                </Link>
              </td>
              {columns.map((c) => {
                const cell = r.cells[c.id];
                return (
                  <td key={c.id} className="ac-cell" title={cell ? `${cell.year}` : "no figure on record"}>
                    {cell ? (
                      <>
                        <span className="ac-bar" aria-hidden="true">
                          <span className="ac-bar-fill" style={{ width: `${Math.max(1.5, (cell.value / max[c.id]) * 100)}%` }} />
                        </span>
                        <span className="ac-cell-v">{cell.text}</span>
                      </>
                    ) : (
                      <span className="ac-none">—</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
