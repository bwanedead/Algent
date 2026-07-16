import type { MetadataRoute } from "next";

import { getAllMeta } from "@/lib/articles";
import { SITE_URL } from "@/lib/site";

// A self-populating site needs machines (indexers) to notice new articles without being told.
export default function sitemap(): MetadataRoute.Sitemap {
  const articles = getAllMeta().map((a) => ({
    url: `${SITE_URL}/articles/${a.slug}`,
    lastModified: a.date || undefined,
  }));
  return [{ url: SITE_URL, lastModified: new Date() }, ...articles];
}
