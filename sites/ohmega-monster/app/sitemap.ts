import type { MetadataRoute } from "next";

import { actorIds } from "@/lib/actors";
import { getAllMeta } from "@/lib/articles";
import { allDailyDates } from "@/lib/daily";
import { dossierIds } from "@/lib/dossier";
import { allBriefSlugs } from "@/lib/intel";
import { indexedPlaceIds } from "@/lib/places";
import { SITE_URL } from "@/lib/site";

// A self-populating site needs machines (indexers) to notice new articles without being told.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const articles = (await getAllMeta()).map((a) => ({
    url: `${SITE_URL}/articles/${a.slug}`,
    lastModified: a.date || undefined,
  }));
  const intel = [
    { url: `${SITE_URL}/articles`, lastModified: new Date() },
    { url: `${SITE_URL}/intel`, lastModified: new Date() },
    { url: `${SITE_URL}/intel/situation`, lastModified: new Date() },
    { url: `${SITE_URL}/intel/briefs`, lastModified: new Date() },
    { url: `${SITE_URL}/intel/actors`, lastModified: new Date() },
    ...(await actorIds()).map((iso) => ({ url: `${SITE_URL}/intel/actors/${iso}`, lastModified: new Date() })),
    { url: `${SITE_URL}/intel/record`, lastModified: new Date() },
    { url: `${SITE_URL}/intel/graph`, lastModified: new Date() },
    ...(await indexedPlaceIds()).map((id) => ({ url: `${SITE_URL}/intel/places/${id}`, lastModified: new Date() })),
    { url: `${SITE_URL}/radar`, lastModified: new Date() },
    { url: `${SITE_URL}/globe`, lastModified: new Date() },
    ...(await allBriefSlugs()).map((slug) => ({ url: `${SITE_URL}/intel/briefs/${slug}` })),
    { url: `${SITE_URL}/intel/theaters`, lastModified: new Date() },
    ...(await dossierIds()).map((id) => ({ url: `${SITE_URL}/intel/theaters/${id}`, lastModified: new Date() })),
    { url: `${SITE_URL}/pulses`, lastModified: new Date() },
    { url: `${SITE_URL}/live`, lastModified: new Date() },
    { url: `${SITE_URL}/developers`, lastModified: new Date() },
    { url: `${SITE_URL}/geopolitics`, lastModified: new Date() },
    ...(await allDailyDates("geopolitics")).map((d) => ({ url: `${SITE_URL}/geopolitics/${d}`, lastModified: d })),
  ];
  return [{ url: SITE_URL, lastModified: new Date() }, ...articles, ...intel];
}
