import Link from "next/link";

import RecordBrowser from "@/components/RecordBrowser";
import { SAID_NOTE } from "@/components/OnRecord";
import type { OnRecord } from "@/lib/record-model";

// A theater's full record: every statement its reports showed, newest first, filterable by speaker.
export default function DossierRecord({ rows }: { rows: OnRecord[] }) {
  if (rows.length === 0) return null;
  return (
    <section className="th-sec" aria-label="On the record">
      <h2 className="geo-h2">On the record ({rows.length})</h2>
      <RecordBrowser rows={rows} fields={["speaker"]} />
      <p className="rec-note">
        {SAID_NOTE} <Link href="/intel/record">The whole record →</Link>
      </p>
    </section>
  );
}
