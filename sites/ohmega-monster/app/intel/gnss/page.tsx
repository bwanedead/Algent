import PageTag from "@/components/PageTag";
import type { Metadata } from "next";
import Link from "next/link";

import GnssView from "@/components/conflict/GnssView";
import { latestZones } from "@/lib/conflict";

import "@/app/daily/daily.css";
import "@/app/situations/situations.css";

export const metadata: Metadata = {
  title: "GPS interference",
  description: "Where aircraft report poor navigation accuracy, a sign of GPS jamming or spoofing: Ohmega's own estimate from ADS-B, cross-checked against GPSJam.",
  alternates: { canonical: "/intel/gnss", types: { "application/json": "/api/v1/gnss" } },
};

// GNSS interference (backend `gnss/`). Ohmega samples ADS-B around known trouble spots every hour; the share of aircraft whose transponder reports
// poor position accuracy (NACp) is the signal. A cell is scored once enough aircraft have been seen, flagged "new" or "intensifying" against its own history, and
// compared with GPSJam's independent daily file. Our estimate is a minimum: only aircraft that broadcast ADS-B and are heard by volunteer receivers appear.
export const revalidate = 1800; // lib/store.ts TTL.daily

export default async function GnssPage() {
  const latest = await latestZones();
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <PageTag kind="data" detail="GPS interference" /> <Link href="/intel/attacks" className="xt">attack log →</Link> <Link href="/globe" className="xt">globe →</Link>
      </p>
      <h1 className="th-claim">GPS interference</h1>
      <p className="th-asof">
        {latest
          ? `Zones where aircraft reported poor navigation accuracy on ${latest.day}. Ohmega's own estimate from ADS-B, shown beside GPSJam's independent file.`
          : "No interference zones have been published yet."}{" "}
        A zone is a sign of jamming or spoofing in the area, not proof of who is doing it.
      </p>
      {latest && <GnssView day={latest.day} zones={latest.zones} baselineSince={latest.baselineSince} baselineDays={latest.baselineDays} history={latest.history} />}
      <p className="th-asof">
        How to read it. Each aircraft&apos;s ADS-B transmitter reports how well it trusts its own position (NACp). Under GPS jamming that trust collapses, so the share of aircraft in a
        one-degree cell reporting NACp below 7 rises. We sample ADS-B (adsb.lol) every hour around known interference regions and some quiet control areas, count only airborne aircraft
        whose positions come from ADS-B itself, and score a cell once enough aircraft have been seen in the day. &quot;New&quot; means a cell that was quiet in its own history; &quot;intensifying&quot;
        means one that was already elevated and now stands out from it. Flags only start after a week of history. GPSJam (gpsjam.org) builds a similar map from the same field with its own
        method; where both show a cell we say so. The live map never shows these cells. Machine access: <Link href="/api/v1/gnss" className="xt">/api/v1/gnss</Link> and the MCP tool <code>get_gnss_interference</code>.
      </p>
    </div>
  );
}
