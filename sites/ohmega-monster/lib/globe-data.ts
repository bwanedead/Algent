import { allDailyDates, claimOf, daily, dayHref, headlineOf, theaterAnchor, type Daily } from "./daily";
import { entityIndex, actorName, textLinker } from "./entities";
import { isoForName } from "./countries";
import type { CountryRow, Dir } from "./globe/channels";
import type { CountryHeadline, CountryInfo, GlobeData, GlobeTheater } from "./globe/data";
import { liveAnomalies } from "./live";

// Builds the /globe page's per-country channel data from what is already published (no model calls, no new documents): the entity
// index (which theaters a state is tied to, and which way they are moving), the recent geopolitics dailies (when each state was
// last named, and the newest headline that names it) and the live anomalies. Server only (reads documents).

const DOMAIN = "geopolitics";
const BASE = "/geopolitics";
const DAILIES = 10; // how far back "recency" looks; anything older reads as not recently covered
const TIES_PER_THEATER = 6; // countries named on a theater's dot
const DIR_ORDER: Dir[] = ["rising", "steady", "easing", "unclear"]; // which direction a country shows when its theaters disagree
const ISO_RE = /^[A-Z]{2}$/;

const dayDiff = (a: string, b: string): number => Math.round((Date.parse(`${a}T00:00:00Z`) - Date.parse(`${b}T00:00:00Z`)) / 86400000);

/** Centre of a theater's map frame, else the mean of the places its developments name. */
function centreOf(t: Daily["theaters"][number]): { lon: number; lat: number } | null {
  const b = t.map?.bbox;
  if (b && b.length === 4 && b.every(Number.isFinite)) return { lon: (b[0] + b[2]) / 2, lat: (b[1] + b[3]) / 2 };
  const pts = t.developments.map((d) => d.place).filter((p): p is NonNullable<typeof p> => !!p && p.lat !== null && p.lon !== null);
  if (pts.length === 0) return null;
  return { lon: pts.reduce((s, p) => s + (p.lon as number), 0) / pts.length, lat: pts.reduce((s, p) => s + (p.lat as number), 0) / pts.length };
}

export async function globeData(): Promise<GlobeData | null> {
  const [idx, dates, linker, anomalies] = await Promise.all([entityIndex(), allDailyDates(DOMAIN), textLinker(), liveAnomalies()]);
  const dailies = (await Promise.all(dates.slice(0, DAILIES).map((d) => daily(DOMAIN, d)))).filter((d): d is Daily => d !== null);
  if (dailies.length === 0) return null;
  const asOf = dailies[0].date;

  const age = new Map<string, number>();
  const headline = new Map<string, CountryHeadline>();
  const seeAge = (iso: string, date: string) => {
    if (!ISO_RE.test(iso)) return;
    const n = dayDiff(asOf, date);
    if (n < (age.get(iso) ?? Infinity)) age.set(iso, n);
  };
  const seeHeadline = (iso: string, text: string, date: string, href: string) => {
    if (ISO_RE.test(iso) && text && !headline.has(iso)) headline.set(iso, { text, date, href });
  };
  for (const d of dailies) { // newest first, so the first headline seen for a state is its newest
    d.theaters.forEach((t, i) => {
      if (t.kind !== "section") return;
      const href = `${dayHref(BASE, d.date, dates)}#${theaterAnchor(t, i)}`;
      const sectionHeadline = t.headline || claimOf(t.bottom_line, 150);
      const named = new Set<string>();
      for (const p of t.pulses) for (const iso of p.actors_iso2) named.add(iso);
      for (const a of t.numbers?.actors ?? []) named.add(a.iso2.toUpperCase());
      for (const iso of Array.from(named)) { seeAge(iso, d.date); seeHeadline(iso, sectionHeadline, d.date, href); }
      for (const dev of t.developments) {
        const isos = new Set<string>();
        for (const a of dev.actors) { const iso = ISO_RE.test(a.trim().toUpperCase()) ? a.trim().toUpperCase() : isoForName(a, linker); if (iso) isos.add(iso); }
        const place = dev.place?.country ? isoForName(dev.place.country, linker) : null;
        if (place) isos.add(place);
        const text = headlineOf(dev.headline, dev.detail, 150) || dev.headline;
        for (const iso of Array.from(isos)) { seeAge(iso, d.date); seeHeadline(iso, text, d.date, href); }
      }
    });
  }

  const hot = new Map<string, number>();
  for (const a of anomalies) if (a.active) for (const c of a.countries) if (ISO_RE.test(c)) hot.set(c, (hot.get(c) ?? 0) + 1);

  // Which theaters each state is tied to.
  const byCountry = new Map<string, { id: string; weight: number }[]>();
  for (const [theater, m] of Array.from(idx.ties)) {
    if (!idx.refs.has(theater)) continue;
    for (const [iso, w] of Array.from(m)) byCountry.set(iso, [...(byCountry.get(iso) ?? []), { id: theater, weight: w }]);
  }

  const countries: Record<string, CountryInfo> = {};
  const codes = new Set<string>([...Array.from(byCountry.keys()), ...Array.from(age.keys()), ...Array.from(hot.keys())]);
  for (const iso of Array.from(codes)) {
    const tied = (byCountry.get(iso) ?? []).sort((a, b) => b.weight - a.weight);
    const theaters = tied.map(({ id }) => idx.refs.get(id)).filter((r): r is NonNullable<typeof r> => !!r)
      .map((r) => ({ id: r.id, name: r.name, dir: r.direction as Dir, href: r.linked ? `/intel/theaters/${r.id}` : "" }));
    const dirs = new Set(theaters.map((t) => t.dir));
    const row: CountryRow = { n: theaters.length, dir: DIR_ORDER.find((d) => dirs.has(d)) ?? null, age: age.get(iso) ?? null, hot: hot.get(iso) ?? 0 };
    countries[iso] = { ...row, name: actorName(idx, iso), theaters, headline: headline.get(iso) ?? null, page: idx.actors.has(iso) || theaters.length > 0 };
  }

  const newest = dailies[0];
  const theaters: GlobeTheater[] = [];
  newest.theaters.forEach((t, i) => {
    if (t.kind !== "section") return;
    const c = centreOf(t);
    const ties = Array.from(idx.ties.get(t.theater_id) ?? []).sort((a, b) => b[1] - a[1]).slice(0, TIES_PER_THEATER).map(([iso]) => iso);
    theaters.push({ id: t.theater_id, name: t.name, dir: t.escalation.direction, heat: t.temperature.heat, lon: c?.lon ?? null, lat: c?.lat ?? null, iso: ties, href: `${dayHref(BASE, newest.date, dates)}#${theaterAnchor(t, i)}`, date: newest.date });
  });
  return { asOf, countries, theaters };
}
