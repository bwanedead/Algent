// Short trails: the backend publishes the last ~2 h of each object's track in shards (`tracks/v<k>` for ships, `tracks/a<k>`
// for aircraft; an object lives in shard `id mod n`). A trail is fetched only when asked for (tap, "trails for visible",
// chokepoint focus) and cached for a few minutes. Client-safe.

import { fetchSnapshot, type TracksDoc } from "@/lib/live-shared";

import { colorOf, type Entity } from "./entities";

export const SHIP_SHARDS = 16; // backend flags.TRACK_SHARDS
export const AIR_SHARDS = 16; // backend flags.AIR_TRACK_SHARDS
const FRESH_MS = 4 * 60 * 1000;
const MAX_TRAILS = 160; // "trails for visible" is capped: more lines than this is a hairball, not information

export type Trail = { key: string; col: string; pts: number[] };

const cache = new Map<string, { at: number; doc: TracksDoc | null }>();

export const shardName = (e: Entity) => (e.kind === "ship" ? `tracks/v${e.id % SHIP_SHARDS}` : `tracks/a${e.id % AIR_SHARDS}`);

async function shard(name: string): Promise<TracksDoc | null> {
  const hit = cache.get(name);
  if (hit && Date.now() - hit.at < FRESH_MS) return hit.doc;
  const doc = await fetchSnapshot<TracksDoc>(name);
  cache.set(name, { at: Date.now(), doc });
  return doc;
}

/** Trails for the given objects (at most MAX_TRAILS; the caller orders them by importance). The object's current position
 *  (`now`) closes each line so it meets the icon. */
export async function loadTrails(ents: Entity[], now: (e: Entity) => [number, number]): Promise<Trail[]> {
  const picked = ents.slice(0, MAX_TRAILS);
  const names = Array.from(new Set(picked.map(shardName)));
  const docs = new Map(await Promise.all(names.map(async (n) => [n, await shard(n)] as const)));
  const out: Trail[] = [];
  for (const e of picked) {
    const pts = docs.get(shardName(e))?.t?.[String(e.id)];
    if (!pts || pts.length < 4) continue;
    out.push({ key: `${e.kind}:${e.id}`, col: colorOf(e), pts: [...pts, ...now(e)] });
  }
  return out;
}
