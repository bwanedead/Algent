// Where the site's published data lives: ONE public URL prefix, the object store's public address (Cloudflare R2).
//
//   NEXT_PUBLIC_DATA_BASE = https://pub-xxxx.r2.dev        (development / first cut-over)
//   NEXT_PUBLIC_DATA_BASE = https://data.ohmega.monster    (production: a custom domain on the bucket, cached at Cloudflare's edge)
//
// The value may carry a path prefix. Vercel's Preview target sets it to the production URL + "/staging" (the staging channel, docs/guides/deploy.md), so a
// preview deployment reads staged data and production data is never the test environment. Nothing else in the site knows about the prefix.
// Objects are addressed by their key: `docs/<path>.gz` (gzipped JSON documents, read by lib/store.ts), `live/...` (map snapshots, polled by
// the browser), `analytics/...` (article images), `satellite/...` (chips). Changing the domain is this one variable. Safe in client and
// server components: it reads only NEXT_PUBLIC_* env. Empty (local dev with no bucket): the site reads its content files instead.

export const DATA_BASE = (process.env.NEXT_PUBLIC_DATA_BASE || "").replace(/\/+$/, "");

/** The public URL of an object key ("live/summary.json" -> "<base>/live/summary.json"). */
export const dataUrl = (key: string): string => `${DATA_BASE}/${key.replace(/^\/+/, "")}`;
