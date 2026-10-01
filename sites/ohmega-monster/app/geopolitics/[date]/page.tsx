import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import DailyReport from "@/components/DailyReport";
import { allDailyDates, daily, fmtDay } from "@/lib/daily";

const DOMAIN = "geopolitics";

type Params = { date: string };

export const dynamicParams = false;

export function generateStaticParams(): Params[] {
  return allDailyDates(DOMAIN).map((date) => ({ date }));
}

export function generateMetadata({ params }: { params: Params }): Metadata {
  const r = daily(DOMAIN, params.date);
  if (!r) return { title: "Geopolitics — daily report" };
  return { title: `Geopolitics — ${fmtDay(r.date)}`, description: r.headline.slice(0, 200) || undefined };
}

export default function GeopoliticsDayPage({ params }: { params: Params }) {
  const report = daily(DOMAIN, params.date);
  if (!report) notFound();
  return (
    <div className="intel-page">
      <Link href="/geopolitics" className="intel-back">
        ← Geopolitics
      </Link>
      <DailyReport report={report} title="Geopolitics" />
    </div>
  );
}
