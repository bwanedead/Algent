import { ageLabel, isStale } from "@/lib/fresh";

import "./fresh.css";

// The as-of age of a product ("2 h ago", "17 days ago"), shown on every hub row and card. It turns dim when the product is late for
// its OWN cadence (lib/fresh.ts: twice the hours it is meant to refresh in), so a once-a-day report 3 days old reads stale while a
// hand-written article 3 days old does not. With `checked` (the product's status file: when its job last ran fine) the age shown is "what's new"
// (`stamp`) but lateness is judged on `checked`, so a quiet product (no new sanctions designation) reads as alive, not stale.
// Server component; renders nothing for a stamp it cannot read.
export default function Age({ stamp, checked, cadenceHours, prefix = "" }: { stamp: string; checked?: string; cadenceHours: number; prefix?: string }) {
  const label = ageLabel(stamp);
  if (!label) return null;
  const stale = isStale(checked || stamp, cadenceHours);
  const last = checked ? ` Checked ${ageLabel(checked) || "recently"}.` : "";
  return (
    <span className={`fresh-age${stale ? " is-stale" : ""}`} title={(stale ? `Late for how often this is made (as of ${stamp.slice(0, 10)}).` : `Last change ${stamp.slice(0, 10)}.`) + last}>
      {prefix}
      {label}
    </span>
  );
}
