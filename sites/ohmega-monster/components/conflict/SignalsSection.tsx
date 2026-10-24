import Link from "next/link";

import { Section } from "@/components/dossier/parts";
import Stat from "@/components/stats/Stat";
import { typeLabel, sharePct, SEVERITY_LABEL, EVENT_SOURCES, type EventSource } from "@/lib/conflict-shared";
import type { SignalAttacks, SignalGnss } from "@/lib/views-types";

// The measured signals over a place or a situation's main states, as two short sections drawn only when there is something to say: "Attacks reported" (the
// strongest events the sources reported lately, from the server-built country / situation view) and "GPS interference" (our zones over the same states on the
// newest day). Both counts are registered stats (attacks_events, gnss_zones): minimums with their basis and limits in the info hover. Server component.

import "@/components/conflict/conflict.css";

const SHOWN = 4;

export default function SignalsSection({ where, attacks, jam }: { where: string; attacks: SignalAttacks | null; jam: SignalGnss | null }) {
  const rows = attacks?.rows ?? [];
  const zones = jam?.zones ?? [];
  return (
    <>
      {attacks && rows.length > 0 && (
        <Section
          id="attacks"
          title="Attacks reported"
          lead={<><Stat id="attacks_events" value={attacks.total} unit window={`in or near ${where}, last ${attacks.window_days ?? 30} days`} /> reported by the sources; the strongest are listed. No source sees every attack.</>}
          aside={<Link href="/intel/attacks" className="xt">attack log →</Link>}
        >
          <ul className="sx-list">
            {rows.slice(0, SHOWN).map((r) => (
              <li key={r.id}>
                {r.on_date} · {typeLabel(r.type)} · {r.place || r.title}
                {r.fatalities !== null && r.fatalities > 0 ? ` · ${r.fatalities} killed per ${EVENT_SOURCES[r.source as EventSource]?.short ?? r.source}` : ""} ·{" "}
                {r.url ? (
                  <a href={r.url} className="xt" rel="noopener noreferrer">{EVENT_SOURCES[r.source as EventSource]?.short ?? r.source} ↗</a>
                ) : (
                  <span>{EVENT_SOURCES[r.source as EventSource]?.short ?? r.source}</span>
                )}
                {r.coding === "machine" ? " · machine-coded" : ""}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {jam && zones.length > 0 && (
        <Section
          id="gps-interference"
          title="GPS interference"
          lead={<><Stat id="gnss_zones" value={jam.total} unit window={`over ${where} on ${jam.day}`} />: aircraft there reported poor navigation accuracy, a sign of jamming or spoofing, not proof of who is responsible.</>}
          aside={<Link href="/intel/gnss" className="xt">all zones →</Link>}
        >
          <ul className="sx-list">
            {zones.slice(0, SHOWN).map((z) => (
              <li key={z.id}>
                {SEVERITY_LABEL[z.severity]} · {sharePct(z.degraded_share)} of {z.aircraft} aircraft observations degraded · {z.lat.toFixed(1)}, {z.lon.toFixed(1)}
                {z.flag ? ` · ${z.flag === "new" ? "new zone" : "intensifying"}` : ""}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}
