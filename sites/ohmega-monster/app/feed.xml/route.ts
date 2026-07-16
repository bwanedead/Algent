import { getAllMeta } from "@/lib/articles";
import { SITE_DESCRIPTION, SITE_NAME, SITE_URL } from "@/lib/site";

// The RSS feed is the contract between "published" and "announced": indexers and readers consume it,
// and the future X-posting pipe can too ("new item in the feed -> compose a post"), fully decoupled
// from the backend. Static — regenerated at build, which is every publish (a commit to site-live).
export const dynamic = "force-static";

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function GET(): Response {
  const items = getAllMeta()
    .map((a) => {
      const url = `${SITE_URL}/articles/${a.slug}`;
      const pubDate = a.date ? `<pubDate>${new Date(a.date).toUTCString()}</pubDate>` : "";
      return `    <item>
      <title>${esc(a.title)}</title>
      <link>${url}</link>
      <guid isPermaLink="true">${url}</guid>
      <description>${esc(a.dek)}</description>
      ${pubDate}
    </item>`;
    })
    .join("\n");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>${esc(SITE_NAME)}</title>
    <link>${SITE_URL}</link>
    <description>${esc(SITE_DESCRIPTION)}</description>
    <atom:link xmlns:atom="http://www.w3.org/2005/Atom" href="${SITE_URL}/feed.xml" rel="self" type="application/rss+xml" />
${items}
  </channel>
</rss>`;

  return new Response(xml, {
    headers: { "Content-Type": "application/rss+xml; charset=utf-8" },
  });
}
