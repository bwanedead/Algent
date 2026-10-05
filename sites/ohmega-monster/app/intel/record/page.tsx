import type { Metadata } from "next";
import Link from "next/link";

import { SAID_NOTE } from "@/components/OnRecord";
import RecordBrowser from "@/components/RecordBrowser";
import ToneChart from "@/components/ToneChart";
import { recordLedger } from "@/lib/record";

import "@/app/geopolitics/geopolitics.css";

export const metadata: Metadata = {
  title: "The record",
  description: "What leaders and institutions said, in their own words, with links to the transcripts. Filter by speaker, side, counterpart, kind and date.",
};

// The whole statements ledger (last 60 days, bounded), browsable. The desk's reports show the few that bear
// on a theater; here is every one. Doctrine: docs/ethos/information-ergonomics-ethos.md.
export default function RecordPage() {
  const ledger = recordLedger();
  return (
    <div className="intel-page geo">
      <p className="geo-micro">
        <Link href="/intel">Situation room</Link> · The record
      </p>
      <h1 className="geo-headline">{ledger && ledger.statements.length > 0 ? `${ledger.statements.length} statements in the last ${ledger.window_days} days, in their own words` : "The record"}</h1>
      {!ledger || ledger.statements.length === 0 ? (
        <p className="intel-empty">No statements have been published yet. Check back soon.</p>
      ) : (
        <>
          <ToneChart series={ledger.tone} />
          <RecordBrowser rows={ledger.statements} />
          <p className="rec-note">
            {SAID_NOTE} Wording is from official transcripts; links go to the original.
          </p>
        </>
      )}
    </div>
  );
}
