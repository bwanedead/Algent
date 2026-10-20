import PageTag from "@/components/PageTag";
import type { Metadata } from "next";
import Link from "next/link";

import AttackLog from "@/components/conflict/AttackLog";
import { eventsSince, recentEvents } from "@/lib/conflict";

import "@/app/geopolitics/geopolitics.css";
import "../theaters/theaters.css";

export const metadata: Metadata = {
  title: "Attack log",
  description: "Attacks, clashes and mass-violence events reported by GDELT, ACLED, UCDP and ReliefWeb, normalised into one record with the source, how it was coded and its limits stated.",
  alternates: { canonical: "/intel/attacks", types: { "application/json": "/api/v1/attacks" } },
};

// The conflict event log (backend `conflict/`, migration 014): GDELT's machine-coded events every 15 minutes (keyless), plus ReliefWeb, ACLED and UCDP once
// their keys are set. Ohmega's own tally of what sources reported, since the day it started collecting: a minimum, not a census. Each row names its source
// and whether software or researchers coded it. (The dated daily reports live under /intel/events/<date>/..., a different thing.)
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function AttacksPage() {
  const [rows, since] = await Promise.all([recentEvents(14), eventsSince()]);
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <PageTag kind="tool" detail="Attack log" /> <Link href="/intel/gnss" className="xt">GPS interference →</Link> <Link href="/intel/maritime" className="xt">maritime behaviour →</Link>
      </p>
      <h1 className="th-claim">Attack log</h1>
      <p className="th-asof">
        {rows.length > 0
          ? `Attacks, clashes and mass-violence events that sources reported in the last 14 days, one record across sources.`
          : "No events have been collected yet."}{" "}
        This is Ohmega&apos;s count of what was reported{since ? `, collected since ${since}` : ""}: no source sees every attack, so every figure here is a minimum.
      </p>
      <AttackLog rows={rows} today={today} since={since} />
      <p className="th-asof">
        How to read it. GDELT rows are machine-coded from news text every 15 minutes: software can count one attack twice, put it in the wrong town or read a figure of speech as
        violence, and it never states casualties. We keep only events geocoded to a city or region, reported by at least two articles, and merge repeats within a couple of days.
        Rows from ACLED and UCDP (when their keys are set) are checked by researchers and carry fatalities; ReliefWeb rows are published humanitarian reports without coordinates.
        &quot;Near&quot; names places in our asset ledger within a few kilometres of the event; it is a proximity, not a claim that the place was hit. Machine access:{" "}
        <Link href="/api/v1/attacks" className="xt">/api/v1/attacks</Link> and the MCP tool <code>get_attack_events</code>.
      </p>
    </div>
  );
}
