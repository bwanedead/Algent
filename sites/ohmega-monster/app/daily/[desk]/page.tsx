import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";

import DeskDay from "@/components/DeskDay";
import DomainSwitch from "@/components/DomainSwitch";
import PageTag from "@/components/PageTag";
import { latestDaily } from "@/lib/daily";
import { dailyBase, deskById, DESKS } from "@/lib/desks";

import "../daily.css";

type Params = { desk: string };

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export function generateStaticParams(): Params[] {
  return DESKS.map((d) => ({ desk: d.id }));
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const desk = deskById(params.desk);
  if (!desk) return { title: "The Daily" };
  return {
    title: `The ${desk.label} Daily`,
    description: desk.blurb,
    alternates: { canonical: dailyBase(desk.id), types: { "application/json": `/api/v1/daily/${desk.id}/latest` } },
  };
}

// The newest report of one desk. Older days live at /daily/<desk>/<date>; the hub of every desk is /daily.
export default async function DeskPage({ params }: { params: Params }) {
  const desk = deskById(params.desk);
  if (!desk) notFound();
  const report = await latestDaily(desk.id);
  if (report) return <DeskDay desk={desk} report={report} />;
  return (
    <div className="intel-page">
      <DomainSwitch current={desk.id} />
      <div className="intel-strip" role="group" aria-label="Report status">
        <span className="intel-strip-title"><PageTag kind="daily" detail={desk.label} /></span>
      </div>
      <p className="intel-empty">No {desk.label} report has been published yet. Check back soon.</p>
      <p className="geo-xlink">
        <Link href="/daily">All dailies →</Link> · <Link href="/data">Data →</Link>
      </p>
    </div>
  );
}
