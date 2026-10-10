/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standard Next on Vercel: content pages are statically generated (SSG), but we keep the door
  // open for dynamic features later (search, charts, personalization) — so NOT `output: 'export'`.
  reactStrictMode: true,

  // The agent feeds (/data/*) are database documents, served by app/feeds/[...path]/route.ts. A rewrite that
  // runs before the filesystem check keeps a stale committed public/data file (the old git-driven feed) from
  // shadowing the live document. Public URLs are unchanged.
  async rewrites() {
    return { beforeFiles: [{ source: "/data/:path*", destination: "/feeds/:path*" }] };
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
