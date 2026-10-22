import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import DailyArchive from "@/components/DailyArchive";
import DomainSwitch from "@/components/DomainSwitch";
import PageTag from "@/components/PageTag";
import { allDailyDates } from "@/lib/daily";
import { dailyBase, deskById, DESKS } from "@/lib/desks";

import "../../daily.css";

type Params = { desk: string };

export const revalidate = 1800; // lib/store.ts TTL.daily: a desk publishes twice a day

export function generateStaticParams(): Params[] {
  return DESKS.map((d) => ({ desk: d.id }));
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const desk = deskById(params.desk);
  return { title: desk ? `${desk.label} Daily: every day` : "The Daily", alternates: { canonical: `${dailyBase(params.desk)}/archive` } };
}

// Every day a desk published, newest first, grouped by month (the same list the day navigator's "All days" popover shows).
export default async function DeskArchivePage({ params }: { params: Params }) {
  const desk = deskById(params.desk);
  if (!desk) notFound();
  const dates = await allDailyDates(desk.id);
  return (
    <div className="intel-page">
      <DomainSwitch current={desk.id} />
      <div className="intel-strip" role="group" aria-label="Archive">
        <span className="intel-strip-title"><PageTag kind="daily" detail={`${desk.label} · every day`} /></span>
      </div>
      {dates.length === 0 ? (
        <p className="intel-empty">No {desk.label} report has been published yet.</p>
      ) : (
        <DailyArchive dates={dates} current="" domain={desk.id} base={dailyBase(desk.id)} />
      )}
      <p className="geo-xlink">
        <Link href="/daily">All dailies →</Link>
      </p>
    </div>
  );
}
