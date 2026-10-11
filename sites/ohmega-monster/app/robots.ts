import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

// Open to crawlers and agents alike, /api included (the read-only agent API, /developers). The sitemap lists the pages.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: ["/", "/api/"] }],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
