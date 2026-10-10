import type { Metadata } from "next";
import { notFound } from "next/navigation";

import RadarView from "@/components/RadarView";
import { getMenu, getMenus, menuLabel } from "@/lib/radar";

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export async function generateStaticParams() {
  return (await getMenus()).map((m) => ({ slug: m.slug }));
}

export async function generateMetadata({ params }: { params: { slug: string } }): Promise<Metadata> {
  const m = await getMenu(params.slug);
  return m ? { title: `Headline radar — ${menuLabel(m)}` } : {};
}

export default async function RadarMenuPage({ params }: { params: { slug: string } }) {
  const m = await getMenu(params.slug);
  if (!m) notFound();
  return <RadarView menu={m} />;
}
