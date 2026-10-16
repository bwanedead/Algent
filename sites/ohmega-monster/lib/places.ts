import { theaterRef, type TheaterRef } from "./entities";
import { assetHistory, getAsset, queryAssets, type GeoAsset, type GeoEvent } from "./geoledger";

// A place as an object (`/intel/places/[id]`): the geoledger's asset, its dated status history, and the theaters whose
// reports put it there. The theaters come from each event's `via` ("daily:<date>:<theater>", how the claim got in), so no
// extra lookup or guess. Server only.

export type PlaceContext = { asset: GeoAsset; history: GeoEvent[]; theaters: TheaterRef[] };

const VIA = /^daily:\d{4}-\d{2}-\d{2}:([\w.-]+)/;

export async function placeContext(id: string): Promise<PlaceContext | null> {
  const asset = await getAsset(id);
  if (!asset) return null;
  const history = await assetHistory(id);
  const ids = Array.from(new Set(history.map((e) => VIA.exec(e.via)?.[1]).filter((t): t is string => !!t)));
  const theaters = await Promise.all(ids.map((t) => theaterRef(t)));
  return { asset, history, theaters };
}

/** Ids of the places worth indexing: those with at least one status event on record. */
export async function indexedPlaceIds(): Promise<string[]> {
  return (await queryAssets({ hasEvents: true, limit: 2000 })).map((a) => a.id);
}
