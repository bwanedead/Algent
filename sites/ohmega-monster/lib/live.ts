import { dbRows, intelDoc } from "@/lib/store";

import { snapshotUrl, type EnergyDoc, type LiveAnomaly, type LiveEvent, type LiveStat, type LiveWorld, type Summary } from "./live-shared";

export * from "./live-shared";

const KINDS: LiveEvent["kind"][] = ["outage", "quake", "aircraft", "fire"];

export async function liveEvents(): Promise<LiveEvent[]> {
  const rows = await dbRows<LiveEvent>("live_events", "select=*&order=starts_at.desc.nullslast&limit=400");
  return rows.filter((e) => KINDS.includes(e.kind));
}

export async function liveStats(): Promise<LiveStat[]> {
  const since = new Date(Date.now() - 45 * 86400000).toISOString().slice(0, 10);
  // kind=neq.presence: live memory's daily means are for the API and the record, not the chokepoint tiles
  return dbRows<LiveStat>("live_stats", `select=*&period=gte.${since}&kind=neq.presence&order=period.asc&limit=4000`);
}

/** Anomalies of the live feeds (migration 011): the ones still going first, then recently closed; [] without a database. */
export async function liveAnomalies(): Promise<LiveAnomaly[]> {
  const rows = await dbRows<LiveAnomaly>("live_anomalies", "select=*&order=active.desc,confidence.desc&limit=200");
  return rows.filter((a) => a.provenance === "ohmega_derived" && (a.direction === "above" || a.direction === "below"));
}

/** The still-going anomalies inside a frame [west, south, east, north] (a theater's map), strongest first. */
export async function anomaliesIn(bbox: number[] | null | undefined): Promise<LiveAnomaly[]> {
  if (!bbox || bbox.length !== 4 || !bbox.every((x) => Number.isFinite(x))) return [];
  const [w, s, e, n] = bbox;
  const rows = (await liveAnomalies()).filter((a) => a.active && a.lat !== null && a.lon !== null && a.lon >= w && a.lon <= e && a.lat >= s && a.lat <= n);
  return rows.sort((a, b) => b.confidence - a.confidence);
}

export async function liveWorld(): Promise<LiveWorld | null> {
  const doc = (await intelDoc("live/world.json")) as Partial<LiveWorld> | null;
  return doc && Array.isArray(doc.bbox) && Array.isArray(doc.countries) && typeof doc.width === "number" && typeof doc.height === "number" ? (doc as LiveWorld) : null;
}

/** A live snapshot from the public Storage bucket for the first paint (the map then polls it); null when unreachable. */
async function snapshot<T>(name: string, revalidate: number): Promise<T | null> {
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL) return null;
  try {
    const res = await fetch(snapshotUrl(name), { next: { revalidate } });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

export const liveSummary = () => snapshot<Summary>("summary", 60);
export const liveEnergy = () => snapshot<EnergyDoc>("energy", 900);
