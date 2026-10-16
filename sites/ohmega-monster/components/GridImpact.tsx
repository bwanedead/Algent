import Link from "next/link";

import {
  ageDays,
  FUEL_LABEL,
  GRID_FUELS,
  mwLabel,
  pctLabel,
  STATUS_LABEL,
  TONE,
  type AssetStatus,
  type GridDoc,
  type GridFuel,
  type GridStance,
} from "@/lib/geoledger-shared";

import "./grid-impact.css";

// Grid-impact panel (backend `geoledger/grid.py`): how much of a country's installed generating capacity has been CLAIMED struck
// (hatched: a party's word), REPORTED damaged, CONFIRMED damaged or destroyed (solid), and RESTORED. Claimed and confirmed overlap
// and are shown as two separate numbers, never added. One bar per fuel on ONE scale (the largest fuel's installed MW), so areas
// compare; segments are each plant counted once at the firmest thing said about it. Original analysis, labelled as Ohmega's.
// Server-rendered, no script: the plant list is a native <details>. Capacity is nameplate, not output.

const SEGMENTS: { key: GridStance; label: string; color: string; hatched: boolean }[] = [
  { key: "confirmed", label: "Confirmed damaged or destroyed", color: TONE.confirmed, hatched: false },
  { key: "reported", label: "Damage reported", color: TONE.reported, hatched: false },
  { key: "claimed", label: "Claimed struck", color: TONE.claimed, hatched: true },
  { key: "restored", label: "Restored", color: TONE.restored, hatched: false },
];

function freshness(day: string): { color: string; text: string } {
  const age = ageDays(day);
  if (age === null) return { color: TONE.neutral, text: "no reports yet" };
  const text = age === 0 ? "last report today" : age === 1 ? "last report yesterday" : `last report ${age} days ago`;
  return { color: age <= 3 ? TONE.restored : age <= 14 ? TONE.claimed : TONE.neutral, text };
}

export default function GridImpact({ grid, name }: { grid: GridDoc; name: string }) {
  const w = grid.windows["30"];
  const short = grid.windows["7"];
  if (!w || !short || w.plants_affected === 0) return null;
  const fuels = GRID_FUELS.filter((f) => grid.installed.by_fuel[f] > 0);
  const scale = Math.max(1, ...fuels.map((f) => grid.installed.by_fuel[f]));
  const fresh = freshness(grid.last_event_on);
  const pct = (mw: number) => `${Math.min(100, (mw / scale) * 100).toFixed(2)}%`;
  const claimed = w.claimed;
  const confirmed = w.confirmed;
  return (
    <section className="gi" aria-label={`Grid impact in ${name}`}>
      <p className="gi-head">
        <span className="geo-micro">Grid impact · Ohmega analysis</span>
        <span className="gi-fresh">
          <span className="gi-dot" aria-hidden="true" style={{ background: fresh.color }} /> {fresh.text}
        </span>
      </p>

      <div className="gi-nums">
        <div className="gi-num">
          <span className="gi-big">{pctLabel(claimed.share)}</span>
          <span className="gi-lab">
            <i className="gi-sw is-hatch" style={{ color: TONE.claimed }} aria-hidden="true" /> claimed struck · {mwLabel(claimed.mw)}
          </span>
          <span className="gi-sub">a party&apos;s own word</span>
        </div>
        <div className="gi-num">
          <span className="gi-big">{pctLabel(confirmed.share)}</span>
          <span className="gi-lab">
            <i className="gi-sw" style={{ background: TONE.confirmed }} aria-hidden="true" /> confirmed damaged · {mwLabel(confirmed.mw)}
          </span>
          <span className="gi-sub">operator, authority or imagery</span>
        </div>
        <div className="gi-num is-small">
          <span className="gi-big">{pctLabel(w.restored.share)}</span>
          <span className="gi-lab">
            <i className="gi-sw" style={{ background: TONE.restored }} aria-hidden="true" /> restored · {mwLabel(w.restored.mw)}
          </span>
        </div>
      </div>
      <p className="gi-cap">
        Last 30 days, of {mwLabel(grid.installed.mw)} installed capacity the ledger knows. Claimed and confirmed overlap; they are not added.
      </p>

      <div className="gi-rows" role="img" aria-label={`Capacity by fuel; ${mwLabel(claimed.mw)} claimed struck and ${mwLabel(confirmed.mw)} confirmed damaged of ${mwLabel(grid.installed.mw)}`}>
        {fuels.map((f: GridFuel) => (
          <div key={f} className="gi-row">
            <span className="gi-fuel">{FUEL_LABEL[f]}</span>
            <span className="gi-track" style={{ width: pct(grid.installed.by_fuel[f]) }}>
              {SEGMENTS.map((s) => {
                const mw = w.buckets[s.key]?.[f] ?? 0;
                return mw > 0 ? (
                  <span
                    key={s.key}
                    className={`gi-seg${s.hatched ? " is-hatch" : ""}`}
                    style={{ width: `${Math.min(100, (mw / grid.installed.by_fuel[f]) * 100).toFixed(2)}%`, ...(s.hatched ? { color: s.color } : { background: s.color }) }}
                    title={`${s.label}: ${mwLabel(mw)} of ${mwLabel(grid.installed.by_fuel[f])} ${FUEL_LABEL[f].toLowerCase()}`}
                  />
                ) : null;
              })}
            </span>
            <span className="gi-val">{mwLabel(grid.installed.by_fuel[f])}</span>
          </div>
        ))}
      </div>
      <ul className="gi-key" aria-label="Key">
        {SEGMENTS.map((s) => (
          <li key={s.key}>
            <i className={`gi-sw${s.hatched ? " is-hatch" : ""}`} style={s.hatched ? { color: s.color } : { background: s.color }} aria-hidden="true" /> {s.label}
          </li>
        ))}
      </ul>

      {short.plants_affected > 0 && (
        <p className="gi-cap">
          Last 7 days: claimed {pctLabel(short.claimed.share)} ({mwLabel(short.claimed.mw)}), confirmed {pctLabel(short.confirmed.share)} ({mwLabel(short.confirmed.mw)}).
        </p>
      )}

      <details className="gi-list">
        <summary>
          <span className="xt">{w.affected.length} plants named</span>
        </summary>
        <ul className="geo-ctx">
          {w.affected.map((p) => (
            <li key={p.id}>
              <span className="geo-micro geo-ctx-when">{p.latest_on.slice(5)}</span>
              <span>
                <Link href={`/intel/places/${p.id}`} className="en-inl">
                  {p.name}
                </Link>{" "}
                <span className="geo-muted">
                  · {p.mw ? mwLabel(p.mw) : "capacity unknown"} {FUEL_LABEL[p.fuel_class].toLowerCase()} ·{" "}
                  <b className="geo-strong">{STATUS_LABEL[(p.latest_status || "unknown") as AssetStatus] ?? p.latest_status}</b>
                  {p.claimants.length > 0 ? ` · said by ${p.claimants.join(", ")}` : ""}
                </span>
              </span>
            </li>
          ))}
        </ul>
      </details>

      <p className="gi-fine">
        Ohmega analysis from the asset ledger and WRI/OpenStreetMap capacity. Capacity is nameplate, not output; a status is not an outage duration; plant coverage is incomplete.
      </p>
    </section>
  );
}
