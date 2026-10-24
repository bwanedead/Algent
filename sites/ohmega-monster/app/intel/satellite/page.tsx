import type { Metadata } from "next";
import Link from "next/link";

import PageTag from "@/components/PageTag";
import SiteCard from "@/components/satellite/SiteCard";
import { bySignal, satelliteDoc } from "@/lib/satellite";

import "@/app/daily/daily.css";
import "@/app/situations/situations.css";

export const metadata: Metadata = {
  title: "Satellite watch",
  description: "Fresh Sentinel-2 imagery of the places the desk tracks, as before and after pairs, with change flagged as a machine signal and night lights compared with each site's own history.",
  alternates: { canonical: "/intel/satellite", types: { "application/json": "/api/v1/satellite" } },
};

// Satellite watch (backend `satellite/`): the places the ledger, today's developments and the maritime chokepoints say matter, each as a before / after
// pair of Sentinel-2 chips of the same ground, with a change score that is a machine signal (never an interpretation), the chip's own cloud share, and
// VIIRS night lights against the site's own earlier nights. The document is rebuilt by the server's daily pass.
export const revalidate = 1800; // lib/store.ts TTL.daily: a desk publishes twice a day

export default async function SatellitePage() {
  const doc = await satelliteDoc();
  const sites = (doc?.sites ?? []).slice().sort(bySignal);
  const shown = sites.filter((s) => s.latest);
  const waiting = sites.filter((s) => !s.latest);
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <PageTag kind="data" detail="Satellite" /> <Link href="/globe" className="xt">globe →</Link>
      </p>
      <h1 className="th-claim">Satellite watch</h1>
      <p className="th-asof">
        {doc
          ? `${doc.counts.with_imagery} of ${doc.counts.watched} watched places have imagery, ${doc.counts.changed} flagged as changed, ${doc.counts.dimmer} dimmer at night. As of ${doc.as_of.slice(0, 16).replace("T", " ")} UTC.`
          : "Nothing has been published yet."}{" "}
        {doc?.read_as}
      </p>
      {shown.length > 0 && (
        <ul className="sat-list" aria-label="Watched places">
          {shown.map((s) => <SiteCard key={s.id} s={s} />)}
        </ul>
      )}
      {waiting.length > 0 && (
        <section className="th-sec" aria-labelledby="sat-wait-h">
          <div className="th-sec-head"><h2 id="sat-wait-h">Watched, no picture yet ({waiting.length})</h2></div>
          <ul className="sat-pending">
            {waiting.map((s) => <li key={s.id}>{s.name}{s.note ? `: ${s.note}` : ""}</li>)}
          </ul>
        </section>
      )}
      <p className="th-asof">
        How the places are chosen: ledger places with a damage statement in the last 30 days (weighted by how firmly it is stated, faded with age), places the
        daily&apos;s developments named in the last two days, and the maritime chokepoints, a dozen at a time, the most overdue first. A place with a dated
        statement is compared against the clearest scene from before it. Pictures are cropped to about 5 km at 20 m a pixel, from the least cloudy of the
        newest scenes, and a pair that is mostly cloud is inconclusive rather than changed. Night lights are NASA VIIRS, a few days behind.
      </p>
      {doc && <p className="th-asof">{doc.credit} Machine access: <Link href="/api/v1/satellite" className="xt">/api/v1/satellite</Link>.</p>}
    </div>
  );
}
