import Link from "next/link";

import FlagRow from "@/components/FlagRow";
import { fmt, type Actor, type Field } from "@/lib/actors";
import { isoToFlagEmoji } from "@/lib/flags";

import "./actors.css";

// Small shared pieces of the actor pages. Server components. One meaning per channel: bar length =
// size on a SHARED scale (never per-row), rank text = position; no colour carries a number.

export function ActorFlag({ iso2, name }: { iso2: string; name: string }) {
  return <FlagRow flags={[isoToFlagEmoji(iso2)]} places={[name]} className="ac-flag" />;
}

/** A bar whose length is value / max: pass the SAME max to every bar that is compared. */
export function ScaleBar({ value, max, label }: { value: number; max: number; label: string }) {
  const w = max > 0 ? Math.max(1.5, Math.min(100, (value / max) * 100)) : 0;
  return (
    <span className="ac-bar" role="img" aria-label={label}>
      <span className="ac-bar-fill" style={{ width: `${w}%` }} />
    </span>
  );
}

export const ordinal = (n: number): string => {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

export const rankText = (f: Field | null): string => (f?.rank && f.of ? `#${f.rank} of ${f.of}` : "");

/** The metrics every strip/table compares, in reading order: id, short label. */
export const COMPARE_METRICS: [string, string][] = [
  ["population", "Population"],
  ["gdp", "GDP"],
  ["gdp_pc", "GDP per person"],
  ["energy_production", "Fossil fuel output"],
  ["milex", "Military spending"],
];

export function headline(a: Actor, id: string): Field | null {
  return a.headline.find((f) => f.id === id) ?? null;
}

/** Actors side by side: one row per metric, one bar per actor, every bar on the metric's shared scale. */
export function ActorScales({ actors }: { actors: Actor[] }) {
  return (
    <div className="ac-scales">
      {COMPARE_METRICS.map(([id, label]) => {
        const rows = actors.map((a) => ({ a, f: headline(a, id) })).filter((r): r is { a: Actor; f: Field } => r.f !== null);
        if (rows.length === 0) return null;
        const max = Math.max(...rows.map((r) => r.f.value));
        return (
          <div key={id} className="ac-scale">
            <p className="ac-scale-k">{label}</p>
            {rows.map(({ a, f }) => (
              <p key={a.iso2} className="ac-scale-row">
                <Link href={`/intel/actors/${a.iso2}`} className="ac-scale-name">
                  {a.name}
                </Link>
                <ScaleBar value={f.value} max={max} label={`${a.name} ${label}: ${fmt(f.value, f.unit)}`} />
                <span className="ac-scale-v" title={`${f.year}`}>
                  {fmt(f.value, f.unit)}
                </span>
              </p>
            ))}
          </div>
        );
      })}
    </div>
  );
}
