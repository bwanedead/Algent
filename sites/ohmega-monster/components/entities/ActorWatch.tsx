import Link from "next/link";

import ComingStrip from "@/components/calendar/ComingStrip";
import SignalsSection from "@/components/conflict/SignalsSection";
import { Section } from "@/components/dossier/parts";
import { Spark } from "@/components/vl/primitives";
import { toComing, type CalendarRow } from "@/lib/calendar-shared";
import { dailyCounts, SOURCES, typeLabel, type SanctionsRow } from "@/lib/sanctions-shared";
import type { SignalAttacks, SignalGnss } from "@/lib/views-types";

// Short sections of an actor page, each drawn only when there is something to say: "Attacks reported" and "GPS interference" (components/conflict/SignalsSection.tsx),
// "Sanctions activity" (how many parties tied to
// this state were added to or removed from the US, UK and EU lists lately, a sparkline of additions per day, the latest few) and
// "Upcoming" (dated items ahead that concern it). Server component; data from lib/sanctions.ts and lib/calendar.ts.

import "@/components/sanctions/sanctions.css";

const SHOWN = 4;

export default function ActorWatch({ name, sanctions, upcoming, today, attacks = null, jam = null }: { name: string; sanctions: SanctionsRow[]; upcoming: CalendarRow[]; today: string; attacks?: SignalAttacks | null; jam?: SignalGnss | null }) {
  const added = sanctions.filter((s) => s.action === "designated");
  const removed = sanctions.length - added.length;
  return (
    <>
      {sanctions.length > 0 && (
        <Section
          id="sanctions"
          title="Sanctions activity"
          lead={`${added.length} ${added.length === 1 ? "party" : "parties"} tied to ${name} added to the US, UK or EU lists in the last 180 days${removed > 0 ? `, ${removed} removed` : ""}.`}
          aside={<Link href="/intel/sanctions" className="xt">all designations →</Link>}
        >
          <p>
            <Spark values={dailyCounts(sanctions, today, 30)} label={`${name}: additions per day, last 30 days`} />
          </p>
          <ul className="sx-list">
            {sanctions.slice(0, SHOWN).map((s) => (
              <li key={s.id}>
                {s.on_date} · {s.action === "designated" ? "added" : "removed"} · {s.name} ({typeLabel(s.type).toLowerCase()}) ·{" "}
                <a href={s.source_url} className="xt" rel="noopener noreferrer">
                  {SOURCES[s.source].short} list ↗
                </a>
              </li>
            ))}
          </ul>
        </Section>
      )}
      <SignalsSection where={name} attacks={attacks} jam={jam} />
      {upcoming.length > 0 && (
        <Section id="upcoming" title="Upcoming" lead={`Dated items ahead that concern ${name}.`}>
          <ComingStrip rows={upcoming.map(toComing)} today={today} heading={`Coming up for ${name}`} limit={6} />
        </Section>
      )}
    </>
  );
}
