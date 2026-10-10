import { intelDoc, intelSlugs } from "./store";

// Headline radar: every synthesis menu the newsroom builds, one JSON document per build
// (radar/<slug>.json), written by the publish pipeline (backend publishing/radar_page.py) to Supabase, with
// content/radar as the transitional fallback (lib/store.ts). Kept forever — the archive is the point.

export type RadarLead = {
  n: number;
  title: string;
  thesis: string;
  pillars: string[];
  kind: string;
  sources: string[];
};

export type RadarMenu = {
  slug: string; // 2026-09-24-2217 (UTC)
  builtAt: string;
  leads: RadarLead[];
};

function parse(d: Record<string, unknown> | null, name: string): RadarMenu | null {
  try {
    if (!d || typeof d !== "object") return null;
    return {
      slug: String(d.slug || name),
      builtAt: String(d.built_at || ""),
      leads: Array.isArray(d.leads)
        ? d.leads.map((l: Record<string, unknown>) => ({
            n: Number(l.n) || 0,
            title: String(l.title ?? ""),
            thesis: String(l.thesis ?? ""),
            pillars: Array.isArray(l.pillars) ? l.pillars.map(String) : [],
            kind: String(l.kind ?? ""),
            sources: Array.isArray(l.sources)
              ? l.sources.map(String).filter((u: string) => /^https?:\/\//.test(u))
              : [],
          }))
        : [],
    };
  } catch {
    return null;
  }
}

/** Every menu, newest first. */
export async function getMenus(): Promise<RadarMenu[]> {
  const names = await intelSlugs("radar");
  const menus = await Promise.all(names.map(async (n) => parse((await intelDoc(`radar/${n}.json`)) as Record<string, unknown> | null, n)));
  return menus
    .filter((m): m is RadarMenu => m !== null && m.leads.length > 0)
    .sort((a, b) => b.slug.localeCompare(a.slug));
}

export async function getMenu(slug: string): Promise<RadarMenu | null> {
  return (await getMenus()).find((m) => m.slug === slug) ?? null;
}

/** "Thu, Sep 24, 2026 · 22:17 UTC" — the build time a reader can place. */
export function menuLabel(m: RadarMenu): string {
  const d = new Date(m.builtAt);
  if (Number.isNaN(d.getTime())) return m.slug;
  const day = d.toLocaleDateString("en-US", {
    weekday: "short", month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
  });
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
  return `${day} · ${time} UTC`;
}

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "source";
  }
}
