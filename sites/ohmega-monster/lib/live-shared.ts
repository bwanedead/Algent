// Client-safe live types and pure helpers (no server imports). Server data access lives in lib/live.ts.
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
  kind: "ships" | "tankers" | "aircraft" | "aircraft_support" | "fires" | "presence"; // presence: live memory's daily means (never a chokepoint tile)
  region: string;
  lat: number | null;
  lon: number | null;
  source_url: string;
};

// ---- anomalies (backend `live/memory`, migration 011): places where the live feeds depart from Ohmega's own learned normal ----

/** One confirmed anomaly. Provenance is always `ohmega_derived`: computed by Ohmega from public sensor feeds, never reported by a source. */
export type LiveAnomaly = {
  id: string;
  series: string; // ship.tanker | air.military | fire.count ...
  layer: "ship" | "air" | "fire";
  klass: string;
  place_kind: "cell" | "gate" | "region" | "fire";
  place_id: string;
  label: string;
  lat: number | null;
  lon: number | null;
  countries: string[];
  direction: "above" | "below";
  starts_at: string;
  ends_at: string | null; // null: still going
  last_seen: string | null;
  active: boolean;
  hours: number;
  value: number;
  normal: number;
  ratio: number | null;
  score: number;
  confidence: number; // 0..1
  learning: boolean; // the baseline is still young
  n_cells: number;
  sentence: string;
  provenance: "ohmega_derived";
  updated_at: string;
};

/** The few fields a compact "unusual" line needs; a LiveAnomaly and a daily's stored rollup row both satisfy it. */
export type UnusualRow = { id: string; sentence: string; direction: "above" | "below"; confidence: number; ongoing: boolean; learning: boolean };

export const toUnusual = (a: LiveAnomaly): UnusualRow => ({ id: a.id, sentence: a.sentence, direction: a.direction, confidence: a.confidence, ongoing: a.ends_at === null, learning: a.learning });

/** Ring colours: above normal warm, below normal cool (also told by the arrow glyph and the words, never colour alone). */
export const ANOMALY_COLOR = { above: "#d4568a", below: "#4a7fd0" } as const;

/** Active first, then the most confident; at most `limit`. */
export function strongest(rows: LiveAnomaly[], limit = 8): LiveAnomaly[] {
  return [...rows].sort((a, b) => Number(b.active) - Number(a.active) || b.confidence - a.confidence).slice(0, limit);
}

/** The simplified world basemap the backend publishes as document `live/world.json`. */
/** `gates` are the ship-counting lines ((lat, lon) ends), keyed by the same region slug as the ship stats; older documents have none. */
export type LiveGate = { region: string; label: string; a: [number, number]; b: [number, number] };
export type LiveWorld = { bbox: [number, number, number, number]; width: number; height: number; countries: { name: string; d: string }[]; gates?: LiveGate[]; credit: string };


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

export const KIND_LABEL: Record<LiveKind, string> = {
  outage: "Internet outages",
  quake: "Earthquakes",
  aircraft: "Military aircraft",
  fire: "Fire hotspots",
};

// ---- snapshot documents (backend `live/snapshots.py`): compact JSON in the public Storage bucket, polled by the map ----------

export const SNAPSHOT_BASE = `${(process.env.NEXT_PUBLIC_SUPABASE_URL || "").replace(/\/+$/, "")}/storage/v1/object/public/published-assets/live`;

/** URL of a live snapshot's plain-JSON form ("fires", "summary", "energy"; the big ones are fetched with `fetchSnapshot`). */
export const snapshotUrl = (name: string) => `${SNAPSHOT_BASE}/${name}.json`;

/** The big documents (vessels, aircraft, coverage, tracks/...) are published gzipped as `<name>.json.gz` (backend `flags.GZIP_LEVEL`). */
export const GZIPPED = ["vessels", "aircraft", "coverage", "tracks/", "points", "tiles/"];

async function inflate(bytes: Uint8Array): Promise<unknown> {
  if (bytes[0] === 0x1f && bytes[1] === 0x8b && typeof DecompressionStream !== "undefined") {
    const stream = new Blob([bytes as BlobPart]).stream().pipeThrough(new DecompressionStream("gzip"));
    return new Response(stream).json();
  }
  return JSON.parse(new TextDecoder().decode(bytes)); // a CDN that already decoded the gzip hands over plain JSON
}

/** Fetch one live snapshot as JSON: the gzipped object first for the big documents (inflated in the browser), the plain `.json` as
 *  the fallback (an older backend, a browser without DecompressionStream). `null` on any failure; the page degrades to "nothing". */
export async function fetchSnapshot<T>(name: string): Promise<T | null> {
  const attempts = GZIPPED.some((g) => name.startsWith(g)) ? [`${SNAPSHOT_BASE}/${name}.json.gz`, snapshotUrl(name)] : [snapshotUrl(name)];
  for (const url of attempts) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (res.ok) return (await inflate(new Uint8Array(await res.arrayBuffer()))) as T;
    } catch {
      /* try the next form */
    }
  }
  return null;
}

/** Receiver coverage: 1-degree cells (id = (floor(lat)+90)*360 + floor(lon)+180) where any AIS position was heard in the last `hours` hours. */
export type CoverageDoc = { as_of: string; deg: number; hours: number; cells: number[] };

export type Headline = { id: string; layer: "outage" | "quake" | "fire" | "ships" | "aircraft"; text: string; score: number; lat: number | null; lon: number | null; zoom: number };
export type GateNow = { label: string; lat: number; lon: number; box?: [number, number, number, number]; in_strait?: number; moving?: number; tankers?: number; transits_today?: number | null; tanker_transits_today?: number | null };
export type Summary = {
  as_of: string;
  headlines: Headline[];
  gates: Record<string, GateNow>;
  fresh: Partial<Record<"outage" | "quake" | "fire" | "ships" | "aircraft" | "aircraft_regions" | "energy", string>>;
  fires?: { as_of?: string; detections?: number; occupied?: number };
};

/** Fire heat: cells are [lon, lat, detections, strongest MW]. */
export type FiresDoc = { as_of: string; cell_deg: number; detections: number; occupied: number; cells: [number, number, number, number][] };

/** Vessel rows: [mmsi, lon, lat, heading (-1 unknown), speed kn (-1 unknown), class, last seen (unix s), name?, destination?, flag?, notable bits?].
 *  Notable bits: 1 military/law enforcement, 2 dark (silent after moving), 4 tanker stopped in a strait. */
export type VesselsDoc = { as_of: string; ttl: number; n: number; classes: string[]; counts: Record<string, number>; rows: (string | number)[][] };
/** Aircraft rows: [id, lon, lat, heading, speed kn, class (0 civil, 1 other mil, 2 tanker, 3 surveillance, 4 airlift, 5 fighter), last seen, callsign?, type?, altitude ft?]. */
export type AircraftDoc = { as_of: string; n: number; classes: string[]; counts: { civil: number; military: number }; rows: (string | number)[][] };
/** World-zoom positions (backend `live/points.py`): per layer `p` is a flat int array, three ints per point `[dlat, lon, c]`, in 0.05 degree
 *  units, delta-coded from the south pole (lon is absolute when dlat > 0, else a step); c = class index + 8 when notable. */
export type PointsLayer = { n: number; counts: Record<string, number>; classes: string[]; p: number[]; flags?: [string, number][] };
export type PointsDoc = { as_of: string; aircraft_as_of: string; deg: number; layers: { vessels: PointsLayer; aircraft: PointsLayer } };
/** Tile index (backend `live/tiles.py`): per layer `{tile id: [rows, etag]}`; tile ids are `r<row>c<col>` over `deg`-degree cells from the south-west corner. */
export type TilesIndex = { as_of: string; aircraft_as_of: string; deg: number; vessels: Record<string, [number, string]>; aircraft: Record<string, [number, string]> };
/** One tile: the same rows as the full documents, for the objects inside it. */
export type TileDoc = { tile: string; n: number; rows: (string | number)[][] };
/** A trail shard: object id -> [lon, lat, lon, lat, ...] oldest first. */
export type TracksDoc = { as_of: string; t: Record<string, number[]> };

export type EnergyTile = { id: string; label: string; unit: string; value: number; as_of_day: string; change_pct: number | null; spark: number[]; source: string; source_url: string };
export type SeriesBlock = { as_of_day: string; value: number; spark: number[]; avg_30d: number | null };
export type EnergyDoc = {
  as_of: string;
  gas: { as_of_day: string; value: number; week_change: number | null; years: { year: number; value: number }[]; spark: (number | null)[]; band: ([number, number] | null)[] } | null;
  lng: { sendout: SeriesBlock | null; full: SeriesBlock | null } | null;
  tiles: EnergyTile[];
  credits: { gas: { text: string; url: string }; lng: { text: string; url: string } };
};

/** "3 min ago" / "2 h ago" from an ISO instant and a clock reading in ms. */
export function ago(iso: string | undefined, nowMs: number): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.round((nowMs - t) / 1000));
  if (s < 90) return "just now";
  const m = Math.round(s / 60);
  if (m < 90) return `${m} min ago`;
  const h = Math.round(m / 60);
  return h < 36 ? `${h} h ago` : `${Math.round(h / 24)} d ago`;
}

/** Compact number: 12,400 -> "12.4k". */
export function compact(n: number): string {
  return n >= 100000 ? `${Math.round(n / 1000)}k` : n >= 10000 ? `${(n / 1000).toFixed(0)}k` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

/** "11 Oct 14:00 UTC" from an ISO instant. */
export function whenUtc(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const mon = d.toLocaleString("en-GB", { month: "short", timeZone: "UTC" });
  return `${d.getUTCDate()} ${mon} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
}
