import type { Metadata } from "next";

import EnergyPanel from "@/components/live/EnergyPanel";
import LiveWorldMap from "@/components/live/LiveWorldMap";
import { liveEnergy, liveEvents, liveStats, liveSummary, liveWorld, whenUtc } from "@/lib/live";

import "./live.css";

export const metadata: Metadata = {
  title: "Live",
  description: "What the world's public sensors show right now: ships and aircraft moving, fire hotspots, earthquakes, internet outages, chokepoint traffic and energy.",
};

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS; the map itself polls the snapshots every minute

export default async function LivePage() {
  const [events, stats, world, summary, energy] = await Promise.all([liveEvents(), liveStats(), liveWorld(), liveSummary(), liveEnergy()]);
  const updated = events.reduce((m, e) => (e.updated_at > m ? e.updated_at : m), "");
  return (
    <div className="intel-page live-page">
      <div className="intel-strip" role="group" aria-label="Live status">
        <span className="intel-strip-title">Live</span>
        <span className="live-muted">{updated ? `events updated ${whenUtc(updated)}` : "no live data yet"}</span>
      </div>
      <h1 className="live-h1">What the world&apos;s public sensors show right now</h1>
      <p className="live-lede">
        Machine readings from free public feeds, refreshed every minute or so. They say that something is happening, not why.
      </p>

      <LiveWorldMap world={world} events={events} stats={stats} summary={summary} />

      <section aria-labelledby="live-energy">
        <h2 id="live-energy" className="live-h2">Energy</h2>
        <EnergyPanel energy={energy} />
      </section>

      <section aria-labelledby="live-limits">
        <h2 id="live-limits" className="live-h2">How to read this</h2>
        <ul className="live-limits">
          <li>Ships and aircraft appear only if they broadcast a position and a volunteer receiver hears it. Many military flights fly silent, so a count is a minimum, and the civil aircraft shown are a sample of the busiest airspace.</li>
          <li>Positions between updates are estimated from each object&apos;s last heading and speed; they snap to the real position at the next update. A trail is the last two hours at most.</li>
          <li>A fire hotspot is a satellite heat reading: a wildfire, an industrial flare or a strike can look the same.</li>
          <li>An internet outage does not say why: a government shutdown, a cut cable and a power failure all look alike.</li>
          <li>Sources: AIS ship positions from aisstream.io, ADS-B from adsb.lol, NASA FIRMS, USGS, IODA (Georgia Tech), GIE AGSI+ and ALSI, delayed market prices. Each event links to its source.</li>
        </ul>
      </section>
    </div>
  );
}
