import { intelDoc, tableDoc, TTL } from "@/lib/store";

import { gate } from "./contract";
import { DATA_BASE } from "./data-base";
import { snapshotUrl, type EnergyDoc, type LiveAnomaly, type LiveEvent, type LiveStat, type LiveWorld, type Summary } from "./live-shared";

export * from "./live-shared";

// Server reads of the live products. They are published FILES now (backend `live/publish.py`, `live/memory/anomalies.py`): `live/events.json`,
// `live/stats.json`, `live/anomalies.json` (documents, `docs/<path>.gz`) and the map's snapshots (`live/<name>.json`, plain objects). Every
// read degrades to "nothing published" (empty list / null) when the file does not exist; a failing bucket throws (lib/store.ts, rule 2).

const KINDS: LiveEvent["kind"][] = ["outage", "quake", "aircraft", "fire"];

export async function liveEvents(): Promise<LiveEvent[]> {
  const doc = await tableDoc<{ events?: LiveEvent[] }>("live/events.json", TTL.live);
  return (doc?.events ?? []).filter((e) => KINDS.includes(e.kind));
}

export async function liveStats(): Promise<LiveStat[]> {
  const doc = await tableDoc<{ stats?: LiveStat[] }>("live/stats.json", TTL.live);
  const since = new Date(Date.now() - 45 * 86400000).toISOString().slice(0, 10);
  // the backend already leaves live memory's daily means (kind "presence") out; the window is enforced here too
  return (doc?.stats ?? []).filter((s) => s.period >= since && s.kind !== "presence");
}

/** Anomalies of the live feeds: the ones still going first, then recently closed; [] when none are published. */
export async function liveAnomalies(): Promise<LiveAnomaly[]> {
  const doc = await tableDoc<{ anomalies?: LiveAnomaly[] }>("live/anomalies.json", TTL.live);
  return (doc?.anomalies ?? []).filter((a) => a.provenance === "ohmega_derived" && (a.direction === "above" || a.direction === "below"));
}

/** The still-going anomalies inside a frame [west, south, east, north] (a theater's map), strongest first. */
export async function anomaliesIn(bbox: number[] | null | undefined): Promise<LiveAnomaly[]> {
  if (!bbox || bbox.length !== 4 || !bbox.every((x) => Number.isFinite(x))) return [];
  const [w, s, e, n] = bbox;
  const rows = (await liveAnomalies()).filter((a) => a.active && a.lat !== null && a.lon !== null && a.lon >= w && a.lon <= e && a.lat >= s && a.lat <= n);
  return rows.sort((a, b) => b.confidence - a.confidence);
}

export async function liveWorld(): Promise<LiveWorld | null> {
  const doc = (await intelDoc("live/world.json", TTL.static)) as Partial<LiveWorld> | null;
  return doc && Array.isArray(doc.bbox) && Array.isArray(doc.countries) && typeof doc.width === "number" && typeof doc.height === "number" ? (doc as LiveWorld) : null;
}

/** A live snapshot from the public bucket for the first paint (the map then polls it); null when it is not published, throws when the
 *  bucket is failing so the last good page is kept. */
async function snapshot<T>(name: string, revalidate: number): Promise<T | null> {
  if (!DATA_BASE) return null;
  let res: Response;
  try {
    res = await fetch(snapshotUrl(name), { next: { revalidate } });
  } catch (err) {
    if (process.env.NEXT_PHASE === "phase-production-build") return null;
    throw new Error(`live snapshot ${name} unreachable: ${(err as Error).message}`);
  }
  if (res.status === 404) return null;
  if (!res.ok) {
    if (process.env.NEXT_PHASE === "phase-production-build") return null;
    throw new Error(`live snapshot ${name} answered ${res.status}`);
  }
  return gate(`live/${name}.json`, (await res.json()) as T);
}

export const liveSummary = () => snapshot<Summary>("summary", TTL.snapshot);
export const liveEnergy = () => snapshot<EnergyDoc>("energy", TTL.maritime);
