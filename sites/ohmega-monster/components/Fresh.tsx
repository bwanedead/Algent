import { ageLabel, isStale } from "@/lib/fresh";

import "./fresh.css";

// The as-of age of a product ("2 h ago", "17 days ago"), shown on every hub row and card. It turns dim when the product is late for
// its OWN cadence (lib/fresh.ts: twice the hours it is meant to refresh in), so a once-a-day report 3 days old reads stale while a
// hand-written article 3 days old does not. Server component; renders nothing for a stamp it cannot read.
export default function Age({ stamp, cadenceHours, prefix = "" }: { stamp: string; cadenceHours: number; prefix?: string }) {
  const label = ageLabel(stamp);
  if (!label) return null;
  const stale = isStale(stamp, cadenceHours);
  return (
    <span className={`fresh-age${stale ? " is-stale" : ""}`} title={stale ? `Late for how often this is made (as of ${stamp.slice(0, 10)})` : `As of ${stamp.slice(0, 10)}`}>
      {prefix}
      {label}
    </span>
  );
}
