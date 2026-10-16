import type { Metadata } from "next";

import EnergyPanel from "@/components/live/EnergyPanel";
import LiveWorldMap from "@/components/live/LiveWorldMap";
import { liveAnomalies, liveEnergy, liveEvents, liveStats, liveSummary, liveWorld, whenUtc } from "@/lib/live";

import "./live.css";

export const metadata: Metadata = {
  title: "Live",
  description: "What the world's public sensors show right now: ships and aircraft moving, fire hotspots, earthquakes, internet outages, chokepoint traffic and energy.",
};

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS; the map itself polls the snapshots every minute

export default async function LivePage() {
  const [events, stats, world, summary, energy, anomalies] = await Promise.all([liveEvents(), liveStats(), liveWorld(), liveSummary(), liveEnergy(), liveAnomalies()]);
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

      <LiveWorldMap world={world} events={events} stats={stats} summary={summary} anomalies={anomalies} />

      <section aria-labelledby="live-energy">
        <h2 id="live-energy" className="live-h2">Energy</h2>
        <EnergyPanel energy={energy} />
      </section>

      <section aria-labelledby="live-limits">
        <h2 id="live-limits" className="live-h2">How to read this</h2>
        <ul className="live-limits">
          <li>Ships and aircraft appear only if they broadcast a position and a volunteer receiver hears it. Many military flights fly silent, so a count is a minimum, and civil coverage is thinner over oceans, Africa, Russia and China, where few receivers listen.</li>
          <li>Ships come from AIS radio receivers on land and coasts, so open ocean is mostly unseen: the shaded cells show where any ship was heard in the last 24 hours, and unshaded sea means no receiver, not no ships.</li>
          <li>Positions between updates are estimated from each object&apos;s last heading and speed; they snap to the real position at the next update. A trail is the last two hours at most.</li>
          <li>Rings and the &quot;Unusual right now&quot; list are Ohmega&apos;s own analysis: counts of ships, aircraft and fire detections per place compared with what that place normally holds at that hour of the week (the median of earlier weeks). They show a pattern departs from normal, not why, and gaps in receiver coverage are screened out. A baseline marked learning is still young.</li>
          <li>A fire hotspot is a satellite heat reading: a wildfire, an industrial flare or a strike can look the same.</li>
          <li>An internet outage does not say why: a government shutdown, a cut cable and a power failure all look alike.</li>
          <li>Sources: AIS ship positions from aisstream.io, Fintraffic (digitraffic.fi, CC 4.0 BY) and the Norwegian Coastal Administration (NLOD), ADS-B aircraft from the OpenSky Network and adsb.lol, NASA FIRMS, USGS, IODA (Georgia Tech), GIE AGSI+ and ALSI, delayed market prices. Each event links to its source.</li>
        </ul>
      </section>
    </div>
  );
}
