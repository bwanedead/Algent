import type { Metadata } from "next";
import { notFound } from "next/navigation";

import HeadlinesView from "@/components/HeadlinesView";
import { getMenu, getMenus, menuLabel } from "@/lib/radar";

export const revalidate = 1800; // lib/store.ts TTL.daily: a desk publishes twice a day

export async function generateStaticParams() {
  return (await getMenus()).map((m) => ({ slug: m.slug }));
}

export async function generateMetadata({ params }: { params: { slug: string } }): Promise<Metadata> {
  const m = await getMenu(params.slug);
  return m ? { title: `Headlines — ${menuLabel(m)}` } : {};
}

export default async function RadarMenuPage({ params }: { params: { slug: string } }) {
  const m = await getMenu(params.slug);
  if (!m) notFound();
  return <HeadlinesView menu={m} />;
}
