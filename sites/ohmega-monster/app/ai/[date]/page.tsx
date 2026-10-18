import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { allDailyDates, daily, fmtDay } from "@/lib/daily";

import "../../geopolitics/geopolitics.css";
import AiDay, { BASE, DOMAIN } from "../AiDay";

type Params = { date: string };

// New days appear without a redeploy: unknown dates render on demand (404 if no report) and are cached.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export async function generateStaticParams(): Promise<Params[]> {
  return (await allDailyDates(DOMAIN)).map((date) => ({ date }));
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const r = await daily(DOMAIN, params.date);
  if (!r) return { title: "The AI Daily" };
  return {
    title: `The AI Daily — ${fmtDay(r.date)}`,
    description: r.headline.slice(0, 200) || undefined,
    alternates: {
      ...((await allDailyDates(DOMAIN))[0] === r.date ? { canonical: BASE } : {}),
      types: { "application/json": `/api/v1/daily/${DOMAIN}/${r.date}` },
    },
  };
}

export default async function AiDayPage({ params }: { params: Params }) {
  const report = await daily(DOMAIN, params.date);
  if (!report) notFound();
  return <AiDay report={report} />;
}
