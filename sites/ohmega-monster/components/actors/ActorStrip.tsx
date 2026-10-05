import Link from "next/link";

import type { Actor } from "@/lib/actors";

import { ActorFlag, ActorScales } from "./ActorParts";

// The theater dossier's "Actors" strip: the theater's actors side by side on shared scales, each
// linking to its page. First screen holds the five most-mentioned; the table of all is one page away.

const SHOWN = 5;

export default function ActorStrip({ actors }: { actors: Actor[] }) {
  if (actors.length === 0) return null;
  const shown = actors.slice(0, SHOWN);
  const names = shown.map((a) => a.name);
  return (
    <section id="actors" className="th-sec" aria-labelledby="actors-h">
      <div className="th-sec-head">
        <h2 id="actors-h">
          {names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}, by the numbers` : `${names[0]}, by the numbers`}
        </h2>
      </div>
      <p className="th-lead ac-chips">
        {shown.map((a) => (
          <Link key={a.iso2} href={`/intel/actors/${a.iso2}`} className="ac-chip">
            <ActorFlag iso2={a.iso2} name={a.name} /> {a.name}
          </Link>
        ))}
        {actors.length > SHOWN && <Link href="/intel/actors">All actors →</Link>}
      </p>
      <ActorScales actors={shown} />
      <p className="th-note">Every bar in a row is on that row&apos;s one scale. Latest year available for each figure; sources on each actor&apos;s page.</p>
    </section>
  );
}
