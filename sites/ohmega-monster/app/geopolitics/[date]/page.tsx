import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { allDailyDates, daily, fmtDay } from "@/lib/daily";

import GeopoliticsDay, { BASE, DOMAIN } from "../GeopoliticsDay";
import "../geopolitics.css";

type Params = { date: string };

// New days appear without a redeploy: unknown dates render on demand (404 if no report) and are cached.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export async function generateStaticParams(): Promise<Params[]> {
  return (await allDailyDates(DOMAIN)).map((date) => ({ date }));
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const r = await daily(DOMAIN, params.date);
  if (!r) return { title: "Geopolitics — daily report" };
  return {
    title: `Geopolitics — ${fmtDay(r.date)}`,
    description: r.headline.slice(0, 200) || undefined,
    // The newest report is one page with two addresses; /geopolitics is the one to index.
    alternates: (await allDailyDates(DOMAIN))[0] === r.date ? { canonical: BASE } : undefined,
  };
}

export default async function GeopoliticsDayPage({ params }: { params: Params }) {
  const report = await daily(DOMAIN, params.date);
  if (!report) notFound();
  return <GeopoliticsDay report={report} />;
}
