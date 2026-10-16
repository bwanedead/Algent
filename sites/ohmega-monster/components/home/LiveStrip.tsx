import Link from "next/link";

import { whenUtc, type Headline, type Summary } from "@/lib/live-shared";

import "./home.css";

// A few headline items from the live feeds, as a quiet strip that opens the live map. Renders nothing
// when the live snapshot is unreachable (never an empty box).
const SHOWN = 4;
const LAYER: Record<Headline["layer"], string> = { outage: "Outage", quake: "Quake", fire: "Fire", ships: "Shipping", aircraft: "Aircraft" };

export default function LiveStrip({ summary }: { summary: Summary | null }) {
  const items = (summary?.headlines ?? []).slice(0, SHOWN);
  if (!summary || items.length === 0) return null;
  return (
    <section className="hm-live" aria-label="Live now">
      <p className="hm-sub">
        Live now <span className="hm-sub-when">{whenUtc(summary.as_of)}</span>{" "}
        <Link href="/live" className="xt">
          open the live map →
        </Link>
      </p>
      <ul>
        {items.map((h) => (
          <li key={h.id}>
            <Link href="/live" className="hm-live-item">
              <span className="hm-live-layer">{LAYER[h.layer] ?? h.layer}</span>
              <span>{h.text}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
