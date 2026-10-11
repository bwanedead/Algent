import type { Metadata } from "next";

import LiveWorldMap from "@/components/live/LiveWorldMap";
import { ChokepointTiles } from "@/components/live/LiveParts";
import { liveEvents, liveStats, liveWorld, shipTiles, whenUtc } from "@/lib/live";

import "./live.css";

export const metadata: Metadata = {
  title: "Live",
  description: "What the world's public sensors show right now: internet outages, earthquakes, military aircraft, fire hotspots and ship traffic at the chokepoints.",
};

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function LivePage() {
  const [events, stats, world] = await Promise.all([liveEvents(), liveStats(), liveWorld()]);
  const tiles = shipTiles(stats);
  const updated = events.reduce((m, e) => (e.updated_at > m ? e.updated_at : m), "");
  const ongoing = events.filter((e) => e.kind === "outage" && e.ends_at === null).length;
  return (
    <div className="intel-page live-page">
      <div className="intel-strip" role="group" aria-label="Live status">
        <span className="intel-strip-title">Live</span>
        <span className="live-muted">{updated ? `updated ${whenUtc(updated)}` : "no live data yet"}</span>
      </div>
      <h1 className="live-h1">What the world&apos;s public sensors show right now</h1>
      <p className="live-lede">
        Machine readings from free public feeds, refreshed every few minutes. They say that something is happening, not why.
        {ongoing > 0 ? ` ${ongoing === 1 ? "1 country is" : `${ongoing} countries are`} in an internet disruption now.` : ""}
      </p>

      <section aria-labelledby="live-choke">
        <h2 id="live-choke" className="live-h2">Chokepoint traffic</h2>
        <p className="live-note">Ships crossing each strait on the last full day, against the recent usual. Our own count.</p>
        <ChokepointTiles tiles={tiles} />
      </section>

      <section aria-labelledby="live-map">
        <h2 id="live-map" className="live-h2">Map</h2>
        <LiveWorldMap world={world} events={events} stats={stats} />
      </section>

      <section aria-labelledby="live-limits">
        <h2 id="live-limits" className="live-h2">How to read this</h2>
        <ul className="live-limits">
          <li>Aircraft and ships appear only if they broadcast a position and a volunteer receiver hears it. Many military flights fly silent, so a count is a minimum.</li>
          <li>A fire hotspot is a satellite heat reading: a wildfire, an industrial flare or a strike can look the same.</li>
          <li>An internet outage does not say why: a government shutdown, a cut cable and a power failure all look alike.</li>
          <li>Sources: IODA (Georgia Tech), USGS, adsb.lol, NASA FIRMS, aisstream.io. Each item links to its source.</li>
        </ul>
      </section>
    </div>
  );
}
