import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import Crumbs, { INTEL_CRUMB } from "@/components/Crumbs";
import { DevelopmentDetail } from "@/components/DailyVisuals";
import { Section } from "@/components/dossier/parts";
import { ActorLink, TheaterLink } from "@/components/entities/EntityLinks";
import PointMap from "@/components/places/PointMap";
import { fmtDay, daily, headlineOf, theaterAnchor } from "@/lib/daily";
import { isoForName } from "@/lib/countries";
import { textLinker, theaterRef } from "@/lib/entities";

import "@/app/geopolitics/geopolitics.css";
import "../../../../theaters/theaters.css";

type Params = { date: string; theater: string; n: string };

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

const DATE = /^\d{4}-\d{2}-\d{2}$/;

/** One development of one theater's section on one day, by its 1-based position; null when any part does not exist. */
async function find(p: Params) {
  const n = Number(p.n);
  if (!DATE.test(p.date) || !Number.isInteger(n) || n < 1) return null;
  const report = await daily("geopolitics", p.date);
  const i = report ? report.theaters.findIndex((t) => t.theater_id === p.theater) : -1;
  if (!report || i < 0) return null;
  const t = report.theaters[i];
  const dev = t.developments[n - 1];
  return dev ? { report, t, i, dev, n } : null;
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const found = await find(params);
  if (!found) return { title: "Development" };
  const { dev, t, report } = found;
  const title = headlineOf(dev.headline, dev.detail, 110) || dev.headline;
  return {
    title: `${title}`,
    description: `${fmtDay(report.date)}, ${t.name}: ${headlineOf(dev.detail, dev.significance, 180) || dev.headline}`,
    alternates: { canonical: `/intel/events/${params.date}/${params.theater}/${params.n}` },
  };
}

// One development of the daily report as an object: what happened, the words and sources it rests on, where, who it names
// and the theater it belongs to. It is the same record the report carries, not a new one.
export default async function EventPage({ params }: { params: Params }) {
  const found = await find(params);
  if (!found) notFound();
  const { report, t, i, dev, n } = found;
  const [theater, linker] = await Promise.all([theaterRef(t.theater_id), textLinker()]);
  const actors = dev.actors.map((name) => ({ name, iso: isoForName(name, linker) }));
  const where = dev.where || [dev.place?.name, dev.place?.country].filter(Boolean).join(", ");
  const pin = dev.place && dev.place.lat !== null && dev.place.lon !== null ? dev.place : null;
  return (
    <div className="intel-page th-page">
      <Crumbs trail={[INTEL_CRUMB, { href: "/geopolitics", label: "Daily report" }]} />
      <p className="th-kicker">
        <span>{fmtDay(report.date)}</span>
        <span>
          <TheaterLink t={theater} />
        </span>
      </p>
      <h1 className="th-claim">{dev.headline}</h1>
      <p className="th-asof">
        Development {n} of {t.developments.length} in this theater&apos;s section.{" "}
        <Link href={`/geopolitics/${report.date}#${theaterAnchor(t, i)}-d${n}`} className="xt">
          See it in the day&apos;s report →
        </Link>
      </p>

      <DevelopmentDetail d={dev} />

      {pin && <PointMap lat={pin.lat as number} lon={pin.lon as number} label={`Map: ${where || dev.headline}`} spread={1.2} note={where ? `${where}.` : ""} />}

      {actors.length > 0 && (
        <Section id="actors" title="Who it names" lead="Open a state to see everything else it is part of.">
          <p className="en-chips">
            {actors.map((a) => (a.iso ? <ActorLink key={a.name} iso2={a.iso} name={a.name} /> : <span key={a.name}>{a.name}</span>))}
          </p>
        </Section>
      )}
    </div>
  );
}
