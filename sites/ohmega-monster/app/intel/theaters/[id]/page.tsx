import type { Metadata } from "next";
import { notFound } from "next/navigation";

import ActorNetwork from "@/components/dossier/ActorNetwork";
import DossierFigures from "@/components/dossier/DossierFigures";
import DossierMap from "@/components/dossier/DossierMap";
import DossierOutlook from "@/components/dossier/DossierOutlook";
import DossierRecord from "@/components/dossier/DossierRecord";
import DossierPulses from "@/components/dossier/DossierPulses";
import DossierTimeline from "@/components/dossier/DossierTimeline";
import { DossierPrimer, DossierTop } from "@/components/dossier/DossierTop";
import { claimOf } from "@/lib/daily";
import { dossier, dossierIds } from "@/lib/dossier";
import { latestSnapshot } from "@/lib/intel";

import "@/app/geopolitics/geopolitics.css";
import "../theaters.css";

type Params = { id: string };

export const dynamicParams = false;

export function generateStaticParams(): Params[] {
  return dossierIds()
    .filter((id) => dossier(id) !== null)
    .map((id) => ({ id }));
}

export function generateMetadata({ params }: { params: Params }): Metadata {
  const d = dossier(params.id);
  if (!d) return { title: "Theater" };
  return {
    title: `${d.name}: dossier`,
    description: (d.current ? claimOf(d.current.bottom_line, 190) : "") || `Everything we know about ${d.name}, and where it is heading.`,
    alternates: { canonical: `/intel/theaters/${d.theater_id}` },
  };
}

// One living page per theater: the claim and its picture first (screen one), then the on-ramp, the
// actors, the record, the numbers and the outlook. Doctrine: docs/ethos/information-ergonomics-ethos.md.
export default function TheaterDossierPage({ params }: { params: Params }) {
  const d = dossier(params.id);
  if (!d) notFound();
  const snap = latestSnapshot();
  const known = new Set(dossierIds());
  const first = d.timeline.map((t) => t.date).filter(Boolean).sort()[0] ?? "";
  return (
    <div className="intel-page th-page">
      <DossierTop d={d} />

      {(d.pulses.length > 0 || d.map) && (
        <div className={`th-screen${d.pulses.length > 0 && d.map ? " is-two" : ""}`}>
          <DossierMap d={d} />
          <DossierPulses pulses={d.pulses} snap={snap} />
        </div>
      )}

      <DossierPrimer primer={d.primer} />
      <ActorNetwork actors={d.actors} relations={d.relations} statements={d.statements} />
      <DossierRecord rows={d.on_record} />
      <DossierTimeline items={d.timeline} since={d.first_seen || first} />
      <DossierFigures figures={d.figures} />
      <DossierOutlook d={d} known={known} />

      <p className="th-built">{d.built_at ? `Rebuilt ${d.built_at.slice(0, 10)}, and again as new reports land.` : "Rebuilt as new reports land."}</p>
    </div>
  );
}
