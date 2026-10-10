import { parseLedger, type RecordLedger } from "./record-model";
import { intelDoc } from "./store";

// The public statements ledger, written by the desk publish as <intel dir>/record.json (ohmega.record/1):
// statements dated within the last `window_days` days (60), newest first, bounded in count, plus per-dyad
// tone series. Read at build time; a missing or malformed file yields null, never a build failure.
export async function recordLedger(): Promise<RecordLedger | null> {
  try {
    return parseLedger(await intelDoc("record.json"));
  } catch {
    return null;
  }
}
