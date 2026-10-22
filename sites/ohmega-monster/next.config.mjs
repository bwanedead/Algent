/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standard Next on Vercel: content pages are statically generated (SSG), but we keep the door
  // open for dynamic features later (search, charts, personalization) — so NOT `output: 'export'`.
  reactStrictMode: true,

  // The agent feeds (/data/<file>.json) are database documents, served by app/feeds/[...path]/route.ts. A rewrite that
  // runs before the filesystem check keeps a stale committed public/data file (the old git-driven feed) from
  // shadowing the live document. Public URLs are unchanged. `:path+` (at least one segment) is deliberate: the Data hub
  // lives at /data exactly (app/data/page.tsx), and `:path*` would swallow it.
  async rewrites() {
    return { beforeFiles: [{ source: "/data/:path+", destination: "/feeds/:path+" }] };
  },

  // The site's shape is Daily / Situations / Articles / Globe / Data (docs/architecture/information-architecture.md). Every retired
  // route keeps working as a permanent redirect, straight to its final address (no chains). The backend still writes some old paths into
  // documents (`/geopolitics/<date>`, `/intel/theaters/<id>`); those resolve here too.
  async redirects() {
    return [
      // Dailies: one hub, one folder per desk.
      { source: "/geopolitics", destination: "/daily/geopolitics", permanent: true },
      { source: "/geopolitics/:date", destination: "/daily/geopolitics/:date", permanent: true },
      { source: "/ai", destination: "/daily/ai", permanent: true },
      { source: "/ai/:date", destination: "/daily/ai/:date", permanent: true },
      { source: "/headlines", destination: "/daily/headlines", permanent: true },
      { source: "/headlines/:slug", destination: "/daily/headlines/:slug", permanent: true },
      { source: "/radar", destination: "/daily/headlines", permanent: true },
      { source: "/radar/:slug", destination: "/daily/headlines/:slug", permanent: true },
      // Situations (was theaters). The briefs index was always a redirect to the theater list.
      { source: "/intel/theaters", destination: "/situations", permanent: true },
      { source: "/intel/theaters/:id", destination: "/situations/:id", permanent: true },
      { source: "/intel/briefs", destination: "/situations", permanent: true },
      // The Intelligence directory is the Data hub.
      { source: "/intel", destination: "/data", permanent: true },
      { source: "/intel/situation", destination: "/data", permanent: true },
    ];
  },

  // Analytic assets are AI-generated SVGs (this covers /public; the Supabase bucket serves its own). In-page they render via <img> (scripts never execute
  // there), and the converter strips active content on copy — but a hardened CSP on the asset path
  // is the FLOOR that closes the whole class (e.g. entity-encoded `java&#115;cript:` a regex misses):
  // served directly, these files run no script and load nothing. The sanitizer stays as the second layer.
  async headers() {
    return [
      {
        source: "/analytics/:path*",
        headers: [
          { key: "Content-Security-Policy", value: "default-src 'none'; style-src 'unsafe-inline'; sandbox" },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
    ];
  },
};

export default nextConfig;
