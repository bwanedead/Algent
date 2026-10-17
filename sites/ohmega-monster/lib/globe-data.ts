import { allDailyDates, claimOf, daily, dayHref, headlineOf, theaterAnchor, type Daily } from "./daily";
import { entityIndex, actorName, textLinker } from "./entities";
import { isoForName } from "./countries";
import { calendarItems } from "./calendar";
import type { CountryRow, Dir } from "./globe/channels";
import type { CountryHeadline, CountryInfo, GlobeData, GlobeTheater } from "./globe/data";
import { decay, THEMES, themeOf, type Theme } from "./globe/themes";
import { liveAnomalies } from "./live";
import { recentSanctions } from "./sanctions";

// Builds the /globe page's per-country channel data from what is already published (no model calls, no new documents): the entity
// index (which theaters a state is tied to, and which way they are moving), the recent geopolitics dailies, sanctions events, the
// forward calendar and the live anomalies (when each state was last named, what about, and the newest headline that names it).
// The theme rule is documented in lib/globe/themes.ts. Server only (reads documents).

const DOMAIN = "geopolitics";
const BASE = "/geopolitics";
const DAILIES = 21; // how many dailies the theme tally and the 7-to-30-day band read (sanctions cover the rest of the 30 days)
const TIES_PER_THEATER = 6; // countries named on a theater's dot
const DIR_ORDER: Dir[] = ["rising", "steady", "easing", "unclear"]; // which direction a country shows when its theaters disagree
const ISO_RE = /^[A-Z]{2}$/;

/** The theme with the largest tally (ties: THEMES order); null when nothing was classified. */
function dominant(m: Map<Theme, number> | undefined): Theme | null {
  if (!m) return null;
  let best: Theme | null = null, bw = 0;
  for (const { id } of THEMES) { const w = m.get(id) ?? 0; if (w > bw) { best = id; bw = w; } }
  return best;
}

/** Centre of a theater's map frame, else the mean of the places its developments name. */
function centreOf(t: Daily["theaters"][number]): { lon: number; lat: number } | null {
  const b = t.map?.bbox;
  if (b && b.length === 4 && b.every(Number.isFinite)) return { lon: (b[0] + b[2]) / 2, lat: (b[1] + b[3]) / 2 };
  const pts = t.developments.map((d) => d.place).filter((p): p is NonNullable<typeof p> => !!p && p.lat !== null && p.lon !== null);
  if (pts.length === 0) return null;
  return { lon: pts.reduce((s, p) => s + (p.lon as number), 0) / pts.length, lat: pts.reduce((s, p) => s + (p.lat as number), 0) / pts.length };
}

export async function globeData(): Promise<GlobeData | null> {
  const nowMs = Date.now();
  const [idx, dates, linker, anomalies, sanctions, calendar] = await Promise.all([
    entityIndex(), allDailyDates(DOMAIN), textLinker(), liveAnomalies(), recentSanctions(30), calendarItems(30),
  ]);
  const dailies = (await Promise.all(dates.slice(0, DAILIES).map((d) => daily(DOMAIN, d)))).filter((d): d is Daily => d !== null);
  if (dailies.length === 0) return null;
  const asOf = dailies[0].date;

  // Per country: newest mention (unix s) and the recency-weighted theme tally.
  const newest = new Map<string, number>();
  const tally = new Map<string, Map<Theme, number>>();
  const headline = new Map<string, CountryHeadline>();
  const see = (iso: string, theme: Theme, base: number, tMs: number | null) => {
    if (!ISO_RE.test(iso)) return;
    if (tMs !== null) {
      const t = Math.round(Math.min(tMs, nowMs) / 1000);
      if (t > (newest.get(iso) ?? 0)) newest.set(iso, t);
    }
    const m = tally.get(iso) ?? new Map<Theme, number>();
    m.set(theme, (m.get(theme) ?? 0) + base * decay(tMs === null ? 0 : (nowMs - tMs) / 86400000));
    tally.set(iso, m);
  };
  const seeHeadline = (iso: string, text: string, date: string, href: string) => {
    if (ISO_RE.test(iso) && text && !headline.has(iso)) headline.set(iso, { text, date, href });
  };
  for (const d of dailies) { // newest first, so the first headline seen for a state is its newest
    const built = Date.parse(d.built_at);
    const tMs = Number.isFinite(built) ? built : Date.parse(`${d.date}T12:00:00Z`);
    d.theaters.forEach((t, i) => {
      if (t.kind !== "section") return;
      const href = `${dayHref(BASE, d.date, dates)}#${theaterAnchor(t, i)}`;
      const sectionHeadline = t.headline || claimOf(t.bottom_line, 150);
      const named = new Set<string>();
      for (const p of t.pulses) for (const iso of p.actors_iso2) named.add(iso);
      for (const a of t.numbers?.actors ?? []) named.add(a.iso2.toUpperCase());
      const sec = themeOf(t.name, sectionHeadline);
      for (const iso of Array.from(named)) { see(iso, sec.theme, sec.base, tMs); seeHeadline(iso, sectionHeadline, d.date, href); }
      for (const dev of t.developments) {
        const isos = new Set<string>();
        for (const a of dev.actors) { const iso = ISO_RE.test(a.trim().toUpperCase()) ? a.trim().toUpperCase() : isoForName(a, linker); if (iso) isos.add(iso); }
        const place = dev.place?.country ? isoForName(dev.place.country, linker) : null;
        if (place) isos.add(place);
        const text = headlineOf(dev.headline, dev.detail, 150) || dev.headline;
        const th = themeOf(t.name, dev.headline, dev.detail);
        for (const iso of Array.from(isos)) { see(iso, th.theme, th.base, tMs); seeHeadline(iso, text, d.date, href); }
      }
    });
  }
  for (const s of sanctions) for (const iso of s.countries) see(iso.toUpperCase(), "economy", 1, Date.parse(`${s.on_date}T12:00:00Z`));
  for (const c of calendar) {
    const theme: Theme = c.kind === "central_bank" ? "economy" : c.kind === "opec" ? "energy" : "politics";
    for (const iso of c.countries) see(iso.toUpperCase(), theme, 0.5, null); // ahead, not new: it tints the theme but never the recency
  }

  const hot = new Map<string, number>();
  for (const a of anomalies) {
    if (!a.active) continue;
    const theme: Theme = a.series.startsWith("ship.tanker") ? "energy" : a.series.startsWith("air.military") ? "conflict" : a.layer === "fire" ? "disaster" : "economy";
    const tMs = Date.parse(a.last_seen ?? a.starts_at);
    for (const c of a.countries) {
      if (!ISO_RE.test(c)) continue;
      hot.set(c, (hot.get(c) ?? 0) + 1);
      see(c, theme, 1, Number.isFinite(tMs) ? tMs : nowMs);
    }
  }

  // Which theaters each state is tied to.
  const byCountry = new Map<string, { id: string; weight: number }[]>();
  for (const [theater, m] of Array.from(idx.ties)) {
    if (!idx.refs.has(theater)) continue;
    for (const [iso, w] of Array.from(m)) byCountry.set(iso, [...(byCountry.get(iso) ?? []), { id: theater, weight: w }]);
  }

  const countries: Record<string, CountryInfo> = {};
  const codes = new Set<string>([...Array.from(byCountry.keys()), ...Array.from(newest.keys()), ...Array.from(hot.keys())]);
  for (const iso of Array.from(codes)) {
    const tied = (byCountry.get(iso) ?? []).sort((a, b) => b.weight - a.weight);
    const theaters = tied.map(({ id }) => idx.refs.get(id)).filter((r): r is NonNullable<typeof r> => !!r)
      .map((r) => ({ id: r.id, name: r.name, dir: r.direction as Dir, href: r.linked ? `/intel/theaters/${r.id}` : "" }));
    const dirs = new Set(theaters.map((t) => t.dir));
    const row: CountryRow = { n: theaters.length, dir: DIR_ORDER.find((d) => dirs.has(d)) ?? null, t: newest.get(iso) ?? null, th: dominant(tally.get(iso)), hot: hot.get(iso) ?? 0 };
    countries[iso] = { ...row, name: actorName(idx, iso), theaters, headline: headline.get(iso) ?? null, page: idx.actors.has(iso) || theaters.length > 0 };
  }

  const top = dailies[0];
  const theaters: GlobeTheater[] = [];
  top.theaters.forEach((t, i) => {
    if (t.kind !== "section") return;
    const c = centreOf(t);
    const ties = Array.from(idx.ties.get(t.theater_id) ?? []).sort((a, b) => b[1] - a[1]).slice(0, TIES_PER_THEATER).map(([iso]) => iso);
    theaters.push({ id: t.theater_id, name: t.name, dir: t.escalation.direction, heat: t.temperature.heat, lon: c?.lon ?? null, lat: c?.lat ?? null, iso: ties, href: `${dayHref(BASE, top.date, dates)}#${theaterAnchor(t, i)}`, date: top.date });
  });
  return { asOf, countries, theaters };
}
