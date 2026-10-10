// Published images. Article hero/figure/chart images live in the PUBLIC Supabase Storage bucket
// `published-assets` (migration 006), written by the backend on publish — so publishing needs no commit.
// A site path like "/analytics/<slug>/hero.webp" becomes
// "<SUPABASE_URL>/storage/v1/object/public/published-assets/analytics/<slug>/hero.webp".
//
// Without NEXT_PUBLIC_SUPABASE_URL (local dev, or before the cut-over) the path is returned unchanged and the
// image is served from /public as before. Set NEXT_PUBLIC_ASSETS_FROM_STORAGE=0 to force the /public path even
// when Supabase is configured (e.g. until the one-off asset backfill has run).
// Safe in client and server components: it reads only NEXT_PUBLIC_* env.

const BASE = (process.env.NEXT_PUBLIC_SUPABASE_URL || "").replace(/\/+$/, "");
const OFF = ["0", "false", "no", "off"].includes((process.env.NEXT_PUBLIC_ASSETS_FROM_STORAGE || "").trim().toLowerCase());

export const BUCKET = "published-assets";

/** Resolve a site asset path ("/analytics/…") to where it is served from. Anything else passes through. */
export function assetUrl(p: string): string {
  if (BASE === "" || OFF || !p.startsWith("/analytics/")) return p; // only published article assets are in the bucket
  return `${BASE}/storage/v1/object/public/${BUCKET}${p}`;
}

/** `assetUrl` as an absolute URL (Open Graph needs one): bucket URLs already are, /public paths get `site`. */
export function absoluteAssetUrl(p: string, site: string): string {
  const u = assetUrl(p);
  return /^https?:\/\//.test(u) ? u : `${site}${u}`;
}
