import type { MetadataRoute } from "next";

import { getAllMeta } from "@/lib/articles";
import { allBriefSlugs } from "@/lib/intel";
import { SITE_URL } from "@/lib/site";

// A self-populating site needs machines (indexers) to notice new articles without being told.
export default function sitemap(): MetadataRoute.Sitemap {
  const articles = getAllMeta().map((a) => ({
    url: `${SITE_URL}/articles/${a.slug}`,
    lastModified: a.date || undefined,
  }));
  const intel = [
    { url: `${SITE_URL}/intel`, lastModified: new Date() },
    ...allBriefSlugs().map((slug) => ({ url: `${SITE_URL}/intel/briefs/${slug}` })),
  ];
  return [{ url: SITE_URL, lastModified: new Date() }, ...articles, ...intel];
}
