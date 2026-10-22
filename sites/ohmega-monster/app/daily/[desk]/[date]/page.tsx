import type { Metadata } from "next";
import { notFound } from "next/navigation";

import DeskDay from "@/components/DeskDay";
import { allDailyDates, daily, fmtDay } from "@/lib/daily";
import { dailyBase, deskById, DESKS } from "@/lib/desks";

import "../../daily.css";

type Params = { desk: string; date: string };

// New days appear without a redeploy: unknown dates render on demand (404 if no report) and are cached.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

const PRERENDERED_DAYS = 3; // per desk; older days render on first request and are then cached (ISR), so a build never reads the whole archive

export async function generateStaticParams(): Promise<Params[]> {
  const perDesk = await Promise.all(DESKS.map(async (d) => (await allDailyDates(d.id)).slice(0, PRERENDERED_DAYS).map((date) => ({ desk: d.id, date }))));
  return perDesk.flat();
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const desk = deskById(params.desk);
  const r = desk ? await daily(desk.id, params.date) : null;
  if (!desk || !r) return { title: "The Daily" };
  return {
    title: `The ${desk.label} Daily — ${fmtDay(r.date)}`,
    description: r.headline.slice(0, 200) || undefined,
    // The newest report is one page with two addresses; /daily/<desk> is the one to index.
    alternates: {
      ...((await allDailyDates(desk.id))[0] === r.date ? { canonical: dailyBase(desk.id) } : {}),
      types: { "application/json": `/api/v1/daily/${desk.id}/${r.date}` },
    },
  };
}

export default async function DeskDayPage({ params }: { params: Params }) {
  const desk = deskById(params.desk);
  if (!desk) notFound();
  const report = await daily(desk.id, params.date);
  if (!report) notFound();
  return <DeskDay desk={desk} report={report} />;
}
