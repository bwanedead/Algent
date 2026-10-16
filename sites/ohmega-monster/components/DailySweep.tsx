import type { DailySweep } from "@/lib/daily";

import IsoFlags from "./IsoFlags";
import { SourceLink } from "./DailyVisuals";

// "Around the world": what the day's focus under-weights, one line per item, grouped by region. Written
// by the backend's world sweep (agents/intel/sweep.py) from material the desk already holds; every item
// rests on a link. The item nominated for a full section wears a "Spotlight" tag. A small world map with
// pins is the follow-up (items carry countries, not coordinates, so it needs a country-level map spec).

const SOURCES_SHOWN = 2;

export default function DailySweepBlock({ sweep }: { sweep: DailySweep }) {
  if (sweep.regions.length === 0) return null;
  return (
    <section className="geo-sweep" aria-label="Around the world">
      <h2 className="geo-h2">Around the world</h2>
      {sweep.regions.map((r) => (
        <div key={r.region} className="geo-sw-region">
          <p className="geo-micro geo-sw-name">{r.region}</p>
          <ul>
            {r.items.map((i, k) => (
              <li key={k} className="geo-sw-item">
                <span className="geo-sw-flags">
                  <IsoFlags codes={i.countries} link />
                </span>
                <span className="geo-sw-line">
                  {i.spotlight && (
                    <span className="geo-sw-tag" title={sweep.spotlight?.section ? "Researched in full above" : "Nominated for a full researched section"}>
                      Spotlight
                    </span>
                  )}
                  {i.text}
                  {i.sources.slice(0, SOURCES_SHOWN).map((u) => (
                    <span key={u}>
                      {" "}
                      <SourceLink url={u} />
                    </span>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
