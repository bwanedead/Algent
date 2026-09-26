import fs from "node:fs";
import path from "node:path";

// Headline radar: every synthesis menu the newsroom builds, one JSON file per build, dropped here by
// the publish pipeline (backend publishing/radar_page.py). Kept forever — the archive is the point.
const RADAR_DIR = path.join(process.cwd(), "content", "radar");

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

function read(file: string): RadarMenu | null {
  try {
    const d = JSON.parse(fs.readFileSync(path.join(RADAR_DIR, file), "utf8"));
    return {
      slug: String(d.slug || file.replace(/\.json$/, "")),
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
export function getMenus(): RadarMenu[] {
  if (!fs.existsSync(RADAR_DIR)) return [];
  return fs
    .readdirSync(RADAR_DIR)
    .filter((f) => f.endsWith(".json"))
    .map(read)
    .filter((m): m is RadarMenu => m !== null && m.leads.length > 0)
    .sort((a, b) => b.slug.localeCompare(a.slug));
}

export function getMenu(slug: string): RadarMenu | null {
  return getMenus().find((m) => m.slug === slug) ?? null;
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
