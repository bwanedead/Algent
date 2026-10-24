// Published images. Article hero/figure/chart images live in the PUBLIC object store (Cloudflare R2), written by the backend on publish -
// so publishing needs no commit. A site path like "/analytics/<slug>/hero.webp" becomes "<NEXT_PUBLIC_DATA_BASE>/analytics/<slug>/hero.webp"
// (lib/data-base.ts).
//
// Without NEXT_PUBLIC_DATA_BASE (local dev, or before the cut-over) the path is returned unchanged and the image is served from /public as
// before. Set NEXT_PUBLIC_ASSETS_FROM_STORAGE=0 to force the /public path even when the bucket is configured (e.g. until the one-off
// `newsroom publish rebuild-all` has run). Safe in client and server components: it reads only NEXT_PUBLIC_* env.

import { DATA_BASE } from "./data-base";

const OFF = ["0", "false", "no", "off"].includes((process.env.NEXT_PUBLIC_ASSETS_FROM_STORAGE || "").trim().toLowerCase());

/** Resolve a site asset path ("/analytics/…") to where it is served from. Anything else passes through. */
export function assetUrl(p: string): string {
  if (DATA_BASE === "" || OFF || !p.startsWith("/analytics/")) return p; // only published article assets are in the bucket
  return `${DATA_BASE}${p}`;
}

/** `assetUrl` as an absolute URL (Open Graph needs one): bucket URLs already are, /public paths get `site`. */
export function absoluteAssetUrl(p: string, site: string): string {
  const u = assetUrl(p);
  return /^https?:\/\//.test(u) ? u : `${site}${u}`;
}
