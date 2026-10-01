import type { Metadata } from "next";
import { notFound } from "next/navigation";

import RadarView from "@/components/RadarView";
import { getMenu, getMenus, menuLabel } from "@/lib/radar";

export function generateStaticParams() {
  return getMenus().map((m) => ({ slug: m.slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const m = getMenu(params.slug);
  return m ? { title: `Headline radar — ${menuLabel(m)}` } : {};
}

export default function RadarMenuPage({ params }: { params: { slug: string } }) {
  const m = getMenu(params.slug);
  if (!m) notFound();
  return <RadarView menu={m} />;
}
