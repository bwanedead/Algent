import type { MetadataRoute } from "next";

import { getAllMeta } from "@/lib/articles";
import { allDailyDates } from "@/lib/daily";
import { dossierIds } from "@/lib/dossier";
import { allBriefSlugs } from "@/lib/intel";
import { SITE_URL } from "@/lib/site";

// A self-populating site needs machines (indexers) to notice new articles without being told.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const articles = (await getAllMeta()).map((a) => ({
    url: `${SITE_URL}/articles/${a.slug}`,
    lastModified: a.date || undefined,
  }));
  const intel = [
    { url: `${SITE_URL}/intel`, lastModified: new Date() },
    ...(await allBriefSlugs()).map((slug) => ({ url: `${SITE_URL}/intel/briefs/${slug}` })),
    { url: `${SITE_URL}/intel/theaters`, lastModified: new Date() },
    ...(await dossierIds()).map((id) => ({ url: `${SITE_URL}/intel/theaters/${id}`, lastModified: new Date() })),
    { url: `${SITE_URL}/pulses`, lastModified: new Date() },
    { url: `${SITE_URL}/geopolitics`, lastModified: new Date() },
    ...(await allDailyDates("geopolitics")).map((d) => ({ url: `${SITE_URL}/geopolitics/${d}`, lastModified: d })),
  ];
  return [{ url: SITE_URL, lastModified: new Date() }, ...articles, ...intel];
}
