import PageTag from "@/components/PageTag";
import type { Metadata } from "next";
import Crumbs, { DATA_CRUMB } from "@/components/Crumbs";
import { SAID_NOTE } from "@/components/OnRecord";
import RecordBrowser from "@/components/RecordBrowser";
import ToneChart from "@/components/ToneChart";
import { recordLedger } from "@/lib/record";
import { shortDate, statView } from "@/lib/stats/render";

import "@/app/daily/daily.css";
import "@/app/situations/situations.css";

export const metadata: Metadata = {
  title: "The record",
  description: "What leaders and institutions said, in their own words, with links to the transcripts. Filter by speaker, side, counterpart, kind and date.",
};

// The whole statements ledger (last 60 days, bounded), browsable. The desk's reports show the few that bear
// on a theater; here is every one. Doctrine: docs/ethos/information-ergonomics-ethos.md.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function RecordPage() {
  const ledger = await recordLedger();
  // The export is capped (backend on_record.MAX_STATEMENTS): show the real window total when the document carries it, else "latest N".
  const n = ledger ? statView({ id: "record_statements", value: ledger.statements.length, cap: { limit: 1500, total: ledger.total } }) : null;
  return (
    <div className="intel-page geo">
      <Crumbs trail={[DATA_CRUMB]} />
      <p className="ptag-row"><PageTag kind="data" detail="The record" /></p>
      <h1 className="geo-headline">{ledger && n && ledger.statements.length > 0 ? `${n.text} statements in the last ${ledger.window_days} days, in their own words` : "The record"}</h1>
      {!ledger || ledger.statements.length === 0 ? (
        <p className="intel-empty">No statements have been published yet. Check back soon.</p>
      ) : (
        <>
          <ToneChart series={ledger.tone} />
          <RecordBrowser rows={ledger.statements} />
          <p className="rec-note">
            {SAID_NOTE} Wording is from official transcripts; links go to the original. Statements are extracted from those texts by a model, only from the feeds we collect
            {ledger.collecting_since ? ` (collecting since ${shortDate(ledger.collecting_since)})` : ""}.
            {ledger.total !== null && ledger.statements.length < ledger.total ? ` The window holds ${ledger.total.toLocaleString("en-US")}; this page lists the latest ${ledger.statements.length.toLocaleString("en-US")}.` : ""}
            {" "}One speaker appears under one spelling.
          </p>
        </>
      )}
    </div>
  );
}
