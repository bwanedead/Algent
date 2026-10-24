import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import Crumbs, { DATA_CRUMB } from "@/components/Crumbs";
import { DevelopmentDetail } from "@/components/DailyVisuals";
import { Section } from "@/components/dossier/parts";
import { ActorLink, TheaterLink } from "@/components/entities/EntityLinks";
import PointMap from "@/components/places/PointMap";
import { fmtDay, headlineOf, parseDevelopment } from "@/lib/daily";
import { dailyHref } from "@/lib/desks";
import { toTheaterRef } from "@/lib/entities";
import { eventView } from "@/lib/views";

import "@/app/daily/daily.css";
import "@/app/situations/situations.css";

type Params = { date: string; theater: string; n: string };

export const revalidate = 1800; // lib/store.ts TTL.daily: a desk publishes twice a day

const DATE = /^\d{4}-\d{2}-\d{2}$/;

/** One development of one theater's section on one day, by its 1-based position; null when any part does not exist. The server builds one small view per
 *  theater-day (its developments, raw, and the state each named actor resolves to), so the page never loads the day's whole report. */
async function find(p: Params) {
  const n = Number(p.n);
  if (!DATE.test(p.date) || !Number.isInteger(n) || n < 1) return null;
  const view = await eventView(p.date, p.theater);
  const dev = view ? parseDevelopment(view.developments[n - 1]) : null;
  return view && dev ? { view, dev, n } : null;
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const found = await find(params);
  if (!found) return { title: "Development" };
  const { dev, view } = found;
  const title = headlineOf(dev.headline, dev.detail, 110) || dev.headline;
  return {
    title: `${title}`,
    description: `${fmtDay(view.date)}, ${view.name}: ${headlineOf(dev.detail, dev.significance, 180) || dev.headline}`,
    alternates: { canonical: `/intel/events/${params.date}/${params.theater}/${params.n}` },
  };
}

// One development of the daily report as an object: what happened, the words and sources it rests on, where, who it names
// and the theater it belongs to. It is the same record the report carries, not a new one.
export default async function EventPage({ params }: { params: Params }) {
  const found = await find(params);
  if (!found) notFound();
  const { view, dev, n } = found;
  const theater = toTheaterRef(view.theater);
  const actors = dev.actors.map((name, k) => ({ name, iso: view.actor_isos[n - 1]?.[k] ?? null }));
  const where = dev.where || [dev.place?.name, dev.place?.country].filter(Boolean).join(", ");
  const pin = dev.place && dev.place.lat !== null && dev.place.lon !== null ? dev.place : null;
  return (
    <div className="intel-page th-page">
      <Crumbs trail={[DATA_CRUMB, { href: "/daily", label: "Daily" }]} />
      <p className="th-kicker">
        <span>{fmtDay(view.date)}</span>
        <span>
          <TheaterLink t={theater} />
        </span>
      </p>
      <h1 className="th-claim">{dev.headline}</h1>
      <p className="th-asof">
        Development {n} of {view.developments.length} in this situation&apos;s section.{" "}
        <Link href={`${dailyHref(view.domain || "geopolitics", view.date)}#${view.anchor}-d${n}`} className="xt">
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
