import type { Metadata } from "next";
import { notFound } from "next/navigation";

import ActorStrip from "@/components/actors/ActorStrip";
import ActorNetwork from "@/components/dossier/ActorNetwork";
import DossierFigures from "@/components/dossier/DossierFigures";
import DossierLineage from "@/components/dossier/DossierLineage";
import DossierMap from "@/components/dossier/DossierMap";
import DossierOutlook from "@/components/dossier/DossierOutlook";
import DossierPulses from "@/components/dossier/DossierPulses";
import DossierRecord from "@/components/dossier/DossierRecord";
import { DossierPrimer, DossierTop } from "@/components/dossier/DossierTop";
import { RelatedTheaters, StatesInvolved } from "@/components/entities/EntityLinks";
import UnusualHere from "@/components/live/UnusualHere";
import SituationStream from "@/components/situations/SituationStream";
import { headlineOf } from "@/lib/daily";
import { situationHref } from "@/lib/desks";
import { dossier, dossierIds, situationIds } from "@/lib/dossier";
import { toTheaterRef } from "@/lib/entities";
import { parseSnapshot } from "@/lib/intel";
import { anomaliesIn, toUnusual } from "@/lib/live";
import { streamOf } from "@/lib/situations";
import { situationView } from "@/lib/views";

import "@/app/daily/daily.css";
import "../situations.css";

type Params = { id: string };

// A situation published after the last deploy renders on demand (dynamicParams stays on): publishing is a database write.
export const revalidate = 1800; // lib/store.ts TTL.daily: a desk publishes twice a day

const PRERENDERED = 8; // each page reads its dossier and its view (the server built the stream); the rest render on first request and are cached (ISR)

export async function generateStaticParams(): Promise<Params[]> {
  return (await situationIds()).slice(0, PRERENDERED).map((id) => ({ id }));
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const d = await dossier(params.id);
  if (!d) return { title: "Situation" };
  return {
    title: `${d.name}: situation`,
    description: (d.current ? headlineOf(d.current.headline, d.current.bottom_line, 190) : "") || `Everything we know about ${d.name}, and where it is heading.`,
    alternates: { canonical: situationHref(d.theater_id), types: { "application/json": `/api/v1/theaters/${d.theater_id}` } },
  };
}

// One living file per situation: the claim first, then THE STREAM (every Daily section about it, newest first; the newest days fully open with their
// pictures, the earlier ones a row into their Daily), then the map, the actors, the record, the numbers and the outlook. The dossier is one document; the
// stream, the actors it involves, the states tied to it and the related situations are one server-built view (backend views/situation.py). Doctrine:
// docs/ethos/information-ergonomics-ethos.md and docs/architecture/information-architecture.md §2.
export default async function SituationPage({ params }: { params: Params }) {
  const d = await dossier(params.id);
  if (!d) notFound();
  const [view, all, linkable, unusual] = await Promise.all([situationView(d.theater_id), dossierIds(), situationIds(), anomaliesIn(d.map?.bbox)]);
  const known = new Set(all);
  const snap = view?.snapshot ? parseSnapshot(view.snapshot, "") : null;
  const stream = streamOf(view);
  const involved = view?.involved ?? [];
  const states = view?.states ?? [];
  const related = (view?.related ?? []).map((r) => ({ ...toTheaterRef(r), shared: r.shared }));
  const briefs = [...d.briefs].sort((a, b) => (a.as_of < b.as_of ? 1 : a.as_of > b.as_of ? -1 : 0));
  return (
    <div className="intel-page th-page">
      <DossierTop d={d} />
      <UnusualHere rows={unusual.map(toUnusual)} asOf="now" />
      <DossierLineage d={d} />

      <DossierPulses pulses={d.pulses} snap={snap} />

      <SituationStream stream={stream} briefs={briefs} snap={snap} dossiers={new Set(linkable)} />

      {d.map && (
        <div className="th-screen">
          <DossierMap d={d} />
        </div>
      )}

      <DossierPrimer primer={d.primer} />
      <ActorNetwork actors={d.actors} relations={d.relations} statements={d.statements} />
      <ActorStrip actors={involved} />
      {states.length > involved.length && <StatesInvolved states={states} />}
      <DossierRecord rows={d.on_record} />
      <DossierFigures figures={d.figures} />
      <DossierOutlook d={d} known={known} />
      <RelatedTheaters items={related} />

      <p className="th-built">{d.built_at ? `Rebuilt ${d.built_at.slice(0, 10)}, and again as new reports land.` : "Rebuilt as new reports land."}</p>
    </div>
  );
}
