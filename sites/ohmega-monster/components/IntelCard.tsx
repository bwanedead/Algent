import Link from "next/link";

import { situationRoom } from "@/lib/situation";
import "@/app/intel/intel.css";

import IsoFlags from "./IsoFlags";
import { Dumbbell } from "./SituationDumbbell";
import { SituationSince, SituationVisitProvider } from "./SituationVisit";

// Home-page teaser for the Situation Room: the biggest moves this week as a mini dumbbell on the
// shared 0–100 axis, plus how many changes are new since the reader's last visit (read-only: only
// /intel records a visit). Falls back to the 30-day moves when the week is quiet.
// Renders nothing until there is data to show.
export default function IntelCard() {
  const room = situationRoom();
  if (!room) return null;
  const top = room.moves["7d"].top.length > 0 ? room.moves["7d"].top : room.moves["30d"].top;
  const shown = top.slice(0, 3).map((m) => ({ id: m.pulse.id, name: m.pulse.title, iso: m.pulse.actors_iso2, from: m.from, to: m.to, delta: m.delta }));
  if (shown.length === 0 && room.changeTimes.length === 0) return null;
  const sign = (d: number) => `${d > 0 ? "▲ +" : "▼ −"}${Math.abs(Math.round(d))}`;
  return (
    <aside className="intel-card sit-card" aria-label="Situation room">
      <SituationVisitProvider touch={false}>
        <Link href="/intel" className="sit-card-link">
          <span className="sit-card-head">
            <span className="intel-micro sit-card-title">Situation room →</span>
            <SituationSince times={room.changeTimes} compact />
          </span>
          {shown.length > 0 && (
            <ul className="sit-card-moves" aria-label="Biggest Pulse moves this week">
              {shown.map((r) => (
                <li key={r.id}>
                  <span className="sit-card-name">
                    <IsoFlags codes={r.iso} />
                    {r.name}
                  </span>
                  <span className="sit-card-chart">
                    <Dumbbell from={r.from} to={r.to} compact label={`${r.name}: ${Math.round(r.from)} to ${Math.round(r.to)}`} />
                  </span>
                  <span className="intel-tab sit-card-delta">{sign(r.delta)}</span>
                </li>
              ))}
            </ul>
          )}
        </Link>
      </SituationVisitProvider>
    </aside>
  );
}
