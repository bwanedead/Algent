import { snapshotUrl } from "./live-shared";
import type { SatelliteDoc } from "./satellite-shared";

export * from "./satellite-shared";

// Server read of the published satellite document (public bucket, `live/satellite.json`). Degrades to null: the page then says nothing has been
// published yet instead of drawing an empty picture. Server-only: client components import lib/satellite-shared.ts.

export async function satelliteDoc(revalidate = 300): Promise<SatelliteDoc | null> {
  try {
    const res = await fetch(snapshotUrl("satellite"), { next: { revalidate } });
    if (!res.ok) return null;
    const doc = (await res.json()) as SatelliteDoc;
    return doc && doc.v === 1 && Array.isArray(doc.sites) ? doc : null;
  } catch {
    return null;
  }
}
