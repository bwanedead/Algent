import fs from "node:fs";
import path from "node:path";

import { parseLedger, type RecordLedger } from "./record-model";

// The public statements ledger, written by the desk publish as <intel dir>/record.json (ohmega.record/1):
// statements dated within the last `window_days` days (60), newest first, bounded in count, plus per-dyad
// tone series. Read at build time; a missing or malformed file yields null, never a build failure.
const INTEL_DIR = process.env.OHMEGA_INTEL_DIR || path.join(process.cwd(), "content", "intel");

export function recordLedger(): RecordLedger | null {
  try {
    return parseLedger(JSON.parse(fs.readFileSync(path.join(INTEL_DIR, "record.json"), "utf8")));
  } catch {
    return null;
  }
}
