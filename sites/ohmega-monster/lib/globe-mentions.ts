import { claimOf, dayHref, headlineOf, theaterAnchor, type Daily } from "./daily";
import { isoForName, type Linker } from "./countries";
import { themeOf, type Theme } from "./globe/themes";

// The one place that decides which countries a daily's sections and developments name, and what theme each reads as. Both the globe's
// map fill (lib/globe-data.ts) and the country panel's brief history (lib/globe-briefs.ts) read this, so a dot in the panel can never
// disagree with the colour the map gave the country. Server only (types from the daily reader).

const ISO_RE = /^[A-Z]{2}$/;
const BASE = "/geopolitics";

export type Mention = {
  kind: "section" | "development";
  isos: string[];
  theme: Theme;
  base: number; // theme weight base (see lib/globe/themes.ts)
  text: string; // one-line headline
  date: string;
  tMs: number; // when the report was built (the recency clock)
  href: string;
};

/** Every section and development of a daily that names a country, in report order. */
export function dailyMentions(d: Daily, dates: string[], linker: Linker | null): Mention[] {
  const built = Date.parse(d.built_at);
  const tMs = Number.isFinite(built) ? built : Date.parse(`${d.date}T12:00:00Z`);
  const out: Mention[] = [];
  d.theaters.forEach((t, i) => {
    if (t.kind !== "section") return;
    const href = `${dayHref(BASE, d.date, dates)}#${theaterAnchor(t, i)}`;
    const sectionHeadline = t.headline || claimOf(t.bottom_line, 150);
    const named = new Set<string>();
    for (const p of t.pulses) for (const iso of p.actors_iso2) named.add(iso);
    for (const a of t.numbers?.actors ?? []) named.add(a.iso2.toUpperCase());
    const sec = themeOf(t.name, sectionHeadline);
    out.push({ kind: "section", isos: Array.from(named).filter((x) => ISO_RE.test(x)), theme: sec.theme, base: sec.base, text: sectionHeadline, date: d.date, tMs, href });
    for (const dev of t.developments) {
      const isos = new Set<string>();
      for (const a of dev.actors) { const iso = ISO_RE.test(a.trim().toUpperCase()) ? a.trim().toUpperCase() : isoForName(a, linker); if (iso) isos.add(iso); }
      const place = dev.place?.country ? isoForName(dev.place.country, linker) : null;
      if (place) isos.add(place);
      const th = themeOf(t.name, dev.headline, dev.detail);
      out.push({ kind: "development", isos: Array.from(isos).filter((x) => ISO_RE.test(x)), theme: th.theme, base: th.base, text: headlineOf(dev.headline, dev.detail, 150) || dev.headline, date: d.date, tMs, href });
    }
  });
  return out;
}
