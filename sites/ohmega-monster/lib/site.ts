// Canonical site identity, in one place. Override the URL per-environment with NEXT_PUBLIC_SITE_URL
// (Vercel preview deployments get their own origin); production is ohmega.monster.
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "https://ohmega.monster").replace(/\/$/, "");
export const SITE_NAME = "Ohmega Monster";
export const SITE_DESCRIPTION = "An information-first newsroom. Reality, with the receipts.";
