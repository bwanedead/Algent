import Link from "next/link";

import { ActorFlag } from "@/components/actors/ActorParts";
import { Overflow, Section } from "@/components/dossier/parts";
import { RecordRow, SAID_NOTE } from "@/components/OnRecord";
import { DIRECTION, dayLabel } from "@/lib/dossier-view";
import type { ActorContext, ActorRef, RelatedActor, RelatedTheater, TheaterRef } from "@/lib/entities";

import "./entities.css";

// The entity graph on the page: countries and theaters linked to each other. Every block here is derived
// by lib/entities.ts from published documents and links only what exists. Server components.

const SHOWN = 6;

/** A country as a link: flag and name, to its actor page. */
export function ActorLink({ iso2, name }: ActorRef) {
  return (
    <Link href={`/intel/actors/${iso2}`} className="en-chip">
      <ActorFlag iso2={iso2} name={name} /> {name}
    </Link>
  );
}

/** A theater as a link when it has a dossier, else plain text; always with its direction. */
export function TheaterLink({ t }: { t: TheaterRef }) {
  const dir = DIRECTION[t.direction];
  return (
    <>
      <span className={`en-dir${t.direction === "rising" || t.direction === "easing" ? " is-moving" : ""}`} title={dir.word}>
        <span aria-hidden="true">{dir.glyph}</span>
        <span className="en-sr"> {dir.word}: </span>
      </span>
      {t.linked ? <Link href={`/intel/theaters/${t.id}`}>{t.name}</Link> : t.name}
    </>
  );
}

/** "Involved in": every theater this state is tied to, with where each stands. */
export function InvolvedIn({ name, theaters }: { name: string; theaters: ActorContext["theaters"] }) {
  if (theaters.length === 0) return null;
  const moving = theaters.filter((t) => t.direction === "rising").length;
  const rows = (list: typeof theaters) => (
    <ul className="en-rows">
      {list.map((t) => (
        <li key={t.id}>
          <TheaterLink t={t} />
        </li>
      ))}
    </ul>
  );
  return (
    <Section
      id="involved-in"
      title={`${name} is involved in ${theaters.length} theater${theaters.length === 1 ? "" : "s"}${moving > 0 ? `, ${moving} escalating` : ""}`}
      lead="Arrows show where each theater is heading. Open one for its dossier."
    >
      {rows(theaters.slice(0, SHOWN))}
      {theaters.length > SHOWN && (
        <Overflow label={`${name}: every theater`} trigger={`${theaters.length - SHOWN} more`}>
          {rows(theaters.slice(SHOWN))}
        </Overflow>
      )}
    </Section>
  );
}

/** "On the record": what the state's officials said lately, then a way to the whole ledger. */
export function ActorOnRecord({ name, said, about }: { name: string; said: ActorContext["said"]; about: number }) {
  if (said.length === 0 && about === 0) return null;
  return (
    <Section
      id="on-record"
      title={said.length > 0 ? `What ${name}'s officials said lately` : `${about} statement${about === 1 ? "" : "s"} about ${name}`}
      lead={
        <>
          {said.length > 0 && <>Newest first. </>}
          {about > 0 && said.length > 0 && (
            <>
              {about} more by others {about === 1 ? "is" : "are"} about {name}.{" "}
            </>
          )}
          <Link href="/intel/record" className="xt">
            The whole record →
          </Link>
        </>
      }
    >
      {said.length > 0 && (
        <>
          <ul className="rec-list">
            {said.map((r) => (
              <RecordRow key={r.id} r={r} />
            ))}
          </ul>
          <p className="th-note">{SAID_NOTE}</p>
        </>
      )}
    </Section>
  );
}

/** Recent developments in the daily reports that name this state. */
export function ActorDevelopments({ name, items }: { name: string; items: ActorContext["developments"] }) {
  if (items.length === 0) return null;
  return (
    <Section id="developments" title={`Recent developments involving ${name}`} lead="From the last few daily reports; each opens that day at that theater.">
      <ul className="en-rows">
        {items.map((d, i) => (
          <li key={i}>
            <span className="en-when">{dayLabel(d.date)}</span>
            <Link href={d.href}>{d.headline}</Link>
            <span className="geo-muted"> · {d.theater}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

/** Relationships: states that share a theater with this one, each labelled by the theaters in common. */
export function RelatedActors({ name, related }: { name: string; related: RelatedActor[] }) {
  if (related.length === 0) return null;
  const list = (items: RelatedActor[]) => (
    <ul className="en-rows">
      {items.map((r) => (
        <li key={r.iso2}>
          <ActorLink iso2={r.iso2} name={r.name} />
          <span className="geo-muted"> · {r.via.map((v) => v.name).join(" · ")}</span>
        </li>
      ))}
    </ul>
  );
  return (
    <Section id="related" title={`Who ${name} shares a theater with`} lead="States named alongside it in the same theater, with the theaters in common.">
      {list(related.slice(0, SHOWN))}
      {related.length > SHOWN && (
        <Overflow label={`${name}: related actors`} trigger={`${related.length - SHOWN} more`}>
          {list(related.slice(SHOWN))}
        </Overflow>
      )}
    </Section>
  );
}

/** On a theater page: the other theaters that share states with it. */
export function RelatedTheaters({ items }: { items: RelatedTheater[] }) {
  if (items.length === 0) return null;
  const list = (rows: RelatedTheater[]) => (
    <ul className="en-rows">
      {rows.map((t) => (
        <li key={t.id}>
          <TheaterLink t={t} />
          <span className="geo-muted">
            {" "}
            · shares {t.shared.slice(0, 4).map((s) => s.name).join(", ")}
            {t.shared.length > 4 ? ` and ${t.shared.length - 4} more` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
  return (
    <Section id="related-theaters" title="Related theaters" lead="Other theaters that involve the same states.">
      {list(items.slice(0, SHOWN))}
      {items.length > SHOWN && (
        <Overflow label="Related theaters" trigger={`${items.length - SHOWN} more`}>
          {list(items.slice(SHOWN))}
        </Overflow>
      )}
      <p className="th-note">
        <Link href="/intel/theaters" className="xt">
          All theaters →
        </Link>
      </p>
    </Section>
  );
}

/** On a theater page: every state it involves, as links to their pages. */
export function StatesInvolved({ states }: { states: ActorRef[] }) {
  if (states.length === 0) return null;
  return (
    <Section id="states" title={`${states.length} state${states.length === 1 ? "" : "s"} involved`} lead="Open one to see everything else it is part of.">
      <p className="en-chips">
        {states.map((s) => (
          <ActorLink key={s.iso2} iso2={s.iso2} name={s.name} />
        ))}
      </p>
    </Section>
  );
}
