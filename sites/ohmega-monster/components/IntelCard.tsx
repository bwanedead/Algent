import Link from "next/link";

import { hottestTheater, latestSnapshot, mostSeverePulses } from "@/lib/intel";

import { BandChip } from "./IntelPulseBoard";

const TREND = { heating: "▲ heating", steady: "◆ steady", cooling: "▼ cooling", new: "● new" } as const;

// Home-page teaser for the Intelligence desk. Renders nothing until there is data to show.
export default function IntelCard() {
  const snap = latestSnapshot();
  const theater = hottestTheater(snap);
  const pulses = mostSeverePulses(snap, 3);
  if (!theater && pulses.length === 0) return null;
  return (
    <aside className="intel-card" aria-label="Intelligence">
      <Link href="/intel" className="intel-card-link">
        <span className="intel-micro intel-card-title">Intelligence →</span>
        {theater && (
          <span className="intel-card-theater">
            <span className="intel-micro">Hottest theater</span>
            <strong>{theater.name}</strong>
            <span className="intel-micro">{TREND[theater.trend]}</span>
          </span>
        )}
        {pulses.length > 0 && (
          <ul className="intel-card-pulses">
            {pulses.map((p) => (
              <li key={p.id}>
                <span className="intel-num intel-num-sm">{Math.round(p.position as number)}</span>
                <span>{p.name}</span>
                <BandChip band={p.band} />
              </li>
            ))}
          </ul>
        )}
      </Link>
    </aside>
  );
}
