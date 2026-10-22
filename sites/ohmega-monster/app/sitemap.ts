import type { MetadataRoute } from "next";

import { actorIds } from "@/lib/actors";
import { getAllMeta } from "@/lib/articles";
import { allDailyDates } from "@/lib/daily";
import { DESKS } from "@/lib/desks";
import { situationIds } from "@/lib/dossier";
import { allBriefSlugs } from "@/lib/intel";
import { indexedPlaceIds } from "@/lib/places";
import { SITE_URL } from "@/lib/site";

// A self-populating site needs machines (indexers) to notice new articles without being told.
export const revalidate = 3600; // lib/store.ts TTL.static: slow products (markets every 4 h, benchmarks every 12 h)

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const articles = (await getAllMeta()).map((a) => ({
    url: `${SITE_URL}/articles/${a.slug}`,
    lastModified: a.date || undefined,
  }));
  const intel = [
    { url: `${SITE_URL}/articles`, lastModified: new Date() },
    { url: `${SITE_URL}/data`, lastModified: new Date() },
    { url: `${SITE_URL}/daily`, lastModified: new Date() },
    { url: `${SITE_URL}/situations`, lastModified: new Date() },
    { url: `${SITE_URL}/intel/actors`, lastModified: new Date() },
    ...(await actorIds()).map((iso) => ({ url: `${SITE_URL}/intel/actors/${iso}`, lastModified: new Date() })),
    { url: `${SITE_URL}/intel/record`, lastModified: new Date() },
    { url: `${SITE_URL}/intel/graph`, lastModified: new Date() },
    ...(await indexedPlaceIds()).map((id) => ({ url: `${SITE_URL}/intel/places/${id}`, lastModified: new Date() })),
    { url: `${SITE_URL}/daily/headlines`, lastModified: new Date() },
    { url: `${SITE_URL}/globe`, lastModified: new Date() },
    ...(await allBriefSlugs()).map((slug) => ({ url: `${SITE_URL}/intel/briefs/${slug}` })),
    ...(await situationIds()).map((id) => ({ url: `${SITE_URL}/situations/${id}`, lastModified: new Date() })),
    { url: `${SITE_URL}/pulses`, lastModified: new Date() },
    { url: `${SITE_URL}/live`, lastModified: new Date() },
    { url: `${SITE_URL}/calendar`, lastModified: new Date() },
    { url: `${SITE_URL}/intel/forecasts`, lastModified: new Date() },
    { url: `${SITE_URL}/intel/sanctions`, lastModified: new Date() },
    { url: `${SITE_URL}/intel/maritime`, lastModified: new Date() },
    { url: `${SITE_URL}/intel/satellite`, lastModified: new Date() },
    { url: `${SITE_URL}/intel/track-record`, lastModified: new Date() },
    { url: `${SITE_URL}/intel/ai`, lastModified: new Date() },
    { url: `${SITE_URL}/developers`, lastModified: new Date() },
    ...DESKS.map((d) => ({ url: `${SITE_URL}/daily/${d.id}`, lastModified: new Date() })),
    ...(await Promise.all(DESKS.map(async (d) => (await allDailyDates(d.id)).map((date) => ({ url: `${SITE_URL}/daily/${d.id}/${date}`, lastModified: date }))))).flat(),
  ];
  return [{ url: SITE_URL, lastModified: new Date() }, ...articles, ...intel];
}
