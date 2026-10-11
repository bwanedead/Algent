import { dbRows, intelDoc } from "@/lib/store";

import type { LiveEvent, LiveStat, LiveWorld } from "./live-shared";

export * from "./live-shared";

const KINDS: LiveEvent["kind"][] = ["outage", "quake", "aircraft", "fire"];

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
