import { dbRows, intelDoc } from "@/lib/store";

// The /live page's data (backend `live/`, migration 007): current events from public live feeds and our own daily
// series computed from them. Everything here degrades to "nothing": no database, an empty table or a failed
// request yields empty lists, and the page says so instead of inventing a picture.

export type LiveKind = "outage" | "quake" | "aircraft" | "fire";
export type LiveSeverity = "info" | "notable" | "major";

export type LiveEvent = {
  id: string;
  feed: string;
  kind: LiveKind;
  title: string;
  detail: string;
  lat: number | null;
  lon: number | null;
  countries: string[];
  severity: LiveSeverity;
  starts_at: string | null;
  ends_at: string | null;
  source_url: string;
  source: string;
  tags: string[];
  data: Record<string, unknown>;
  updated_at: string;
};

export type LiveStat = {
  series_id: string;
  period: string; // YYYY-MM-DD
  value: number;
  partial: boolean; // the day still being counted
  name: string;
  unit: string;
  kind: "ships" | "tankers" | "aircraft" | "aircraft_support" | "fires";
  region: string;
  lat: number | null;
  lon: number | null;
  source_url: string;
};

/** The simplified world basemap the backend publishes as document `live/world.json`. */
export type LiveWorld = { bbox: [number, number, number, number]; width: number; height: number; countries: { name: string; d: string }[]; credit: string };

const KINDS: LiveKind[] = ["outage", "quake", "aircraft", "fire"];

export async function liveEvents(): Promise<LiveEvent[]> {
  const rows = await dbRows<LiveEvent>("live_events", "select=*&order=starts_at.desc.nullslast&limit=400");
  return rows.filter((e) => KINDS.includes(e.kind));
}

export async function liveStats(): Promise<LiveStat[]> {
  const since = new Date(Date.now() - 45 * 86400000).toISOString().slice(0, 10);
  return dbRows<LiveStat>("live_stats", `select=*&period=gte.${since}&order=period.asc&limit=4000`);
}

export async function liveWorld(): Promise<LiveWorld | null> {
  const doc = (await intelDoc("live/world.json")) as Partial<LiveWorld> | null;
  return doc && Array.isArray(doc.bbox) && Array.isArray(doc.countries) && typeof doc.width === "number" && typeof doc.height === "number" ? (doc as LiveWorld) : null;
}

// ---- chokepoint tiles: our own daily ship count against its recent normal -------------------------------------

export type Tile = { region: string; name: string; latest: number; latestDay: string; usual: number | null; pct: number | null; tankers: number | null; days: number[] };

const MIN_DAYS_FOR_USUAL = 5; // fewer completed days than this and "usual" would be a guess: say nothing instead

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** One tile per chokepoint that has at least one completed day. "Usual" = median of the completed days before the latest
 *  one (up to 14). Partial days never enter: a half-counted today is not a collapse. */
export function shipTiles(stats: LiveStat[]): Tile[] {
  const by = new Map<string, LiveStat[]>();
  for (const s of stats) if (s.kind === "ships" && !s.partial) by.set(s.region, [...(by.get(s.region) ?? []), s]);
  const tanker = new Map<string, LiveStat[]>();
  for (const s of stats) if (s.kind === "tankers" && !s.partial) tanker.set(s.region, [...(tanker.get(s.region) ?? []), s]);
  const out: Tile[] = [];
  for (const [region, rows] of Array.from(by.entries())) {
    const days = rows.sort((a, b) => a.period.localeCompare(b.period));
    const last = days[days.length - 1];
    const before = days.slice(-15, -1).map((d) => d.value);
    const usual = before.length >= MIN_DAYS_FOR_USUAL ? median(before) : null;
    const t = (tanker.get(region) ?? []).find((x) => x.period === last.period);
    out.push({
      region,
      name: last.name.split(" — ")[0],
      latest: last.value,
      latestDay: last.period,
      usual,
      pct: usual && usual > 0 ? Math.round(((last.value - usual) / usual) * 100) : null,
      tankers: t ? t.value : null,
      days: days.slice(-30).map((d) => d.value),
    });
  }
  return out.sort((a, b) => a.name.localeCompare(b.name));
}

// ---- matching events to a theater by the countries its text names -------------------------------------------

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Live events still going whose countries are named in `text` (a theater's name and assessment). Word-boundary match on
 *  the country name; short names must be capitalised ("US" is not "us"). Ended outages and quiet ones are left out. */
export function liveTouching(events: LiveEvent[], text: string, limit = 4): LiveEvent[] {
  const hit = events.filter(
    (e) =>
      e.ends_at === null &&
      e.countries.some((c) => (c.length <= 3 ? new RegExp(`\\b${escapeRe(c)}\\b`) : new RegExp(`\\b${escapeRe(c)}`, "i")).test(text)),
  );
  const rank = { major: 0, notable: 1, info: 2 } as const;
  return hit.sort((a, b) => rank[a.severity] - rank[b.severity]).slice(0, limit);
}

export const KIND_LABEL: Record<LiveKind, string> = {
  outage: "Internet outages",
  quake: "Earthquakes",
  aircraft: "Military aircraft",
  fire: "Fire hotspots",
};

/** "11 Oct 14:00 UTC" from an ISO instant. */
export function whenUtc(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const mon = d.toLocaleString("en-GB", { month: "short", timeZone: "UTC" });
  return `${d.getUTCDate()} ${mon} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
}
