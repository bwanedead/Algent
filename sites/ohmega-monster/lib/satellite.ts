import { gate } from "./contract";
import { DATA_BASE } from "./data-base";
import { snapshotUrl } from "./live-shared";
import type { SatelliteDoc } from "./satellite-shared";
import { TTL } from "./store";

export * from "./satellite-shared";

// Server read of the published satellite document (public bucket, `live/satellite.json`). Null when nothing is published: the page then says so
// instead of drawing an empty picture. A failing bucket throws, so the last good page is kept (lib/store.ts, rule 2).
// Server-only: client components import lib/satellite-shared.ts.

export async function satelliteDoc(revalidate: number = TTL.daily): Promise<SatelliteDoc | null> {
  if (!DATA_BASE) return null;
  let res: Response;
  try {
    res = await fetch(snapshotUrl("satellite"), { next: { revalidate } });
  } catch (err) {
    if (process.env.NEXT_PHASE === "phase-production-build") return null;
    throw new Error(`satellite document unreachable: ${(err as Error).message}`);
  }
  if (res.status === 404) return null;
  if (!res.ok) {
    if (process.env.NEXT_PHASE === "phase-production-build") return null;
    throw new Error(`satellite document answered ${res.status}`);
  }
  const doc = gate("live/satellite.json", (await res.json()) as SatelliteDoc);
  return doc && doc.v === 1 && Array.isArray(doc.sites) ? doc : null;
}
