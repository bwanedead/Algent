import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { allDailyDates, daily, fmtDay } from "@/lib/daily";

import GeopoliticsDay, { BASE, DOMAIN } from "../GeopoliticsDay";
import "../geopolitics.css";

type Params = { date: string };

export const dynamicParams = false;

export function generateStaticParams(): Params[] {
  return allDailyDates(DOMAIN).map((date) => ({ date }));
}

export function generateMetadata({ params }: { params: Params }): Metadata {
  const r = daily(DOMAIN, params.date);
  if (!r) return { title: "Geopolitics — daily report" };
  return {
    title: `Geopolitics — ${fmtDay(r.date)}`,
    description: r.headline.slice(0, 200) || undefined,
    // The newest report is one page with two addresses; /geopolitics is the one to index.
    alternates: allDailyDates(DOMAIN)[0] === r.date ? { canonical: BASE } : undefined,
  };
}

export default function GeopoliticsDayPage({ params }: { params: Params }) {
  const report = daily(DOMAIN, params.date);
  if (!report) notFound();
  return <GeopoliticsDay report={report} />;
}
