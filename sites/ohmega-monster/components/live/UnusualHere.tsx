import Link from "next/link";

import "@/app/live/live.css";

import Glyph from "@/components/vl/Glyph";
import { ANOMALY_COLOR, type UnusualRow } from "@/lib/live-shared";

// "Unusual in this theater": the few places Ohmega's own live memory (backend `live/memory`) finds ships, aircraft or fires outside their
// learned normal in this theater's countries or frame. A daily passes the rollup it stored for that day (so an archived report keeps
// the day's picture), a dossier passes what is flagged now. Pure and server-safe; draws nothing when nothing is flagged.

const SHOWN = 4;

export default function UnusualHere({ rows, asOf = "" }: { rows: UnusualRow[]; asOf?: string }) {
  if (rows.length === 0) return null;
  return (
    <aside className="live-here" aria-label="Unusual in this theater">
      <p className="live-here-head">
        Unusual in this theater{asOf ? ` · ${asOf}` : ""} <Link href="/live" className="xt">live map →</Link>
      </p>
      <ul>
        {rows.slice(0, SHOWN).map((r) => (
          <li key={r.id}>
            <span className="live-here-glyph" style={{ color: ANOMALY_COLOR[r.direction] }} aria-hidden="true">
              <Glyph name={r.direction === "above" ? "up" : "down"} size={12} />
            </span>
            <span>
              {r.sentence}
              {!r.ongoing && <span className="live-muted"> (ended)</span>}
              {r.learning && <span className="live-muted"> (young baseline)</span>}
            </span>
          </li>
        ))}
      </ul>
      <p className="live-muted">Ohmega analysis against its own learned normal for the hour of the week, from public ship, aircraft and satellite feeds. It shows a pattern departs from normal, not why.</p>
    </aside>
  );
}
