import { toTheaterRef, type TheaterRef } from "./entities";
import { getAsset, queryAssets, toAsset, toEvent, type GeoAsset, type GeoEvent } from "./geoledger";
import { entityView } from "./views";

// A place as an object (`/intel/places/[id]`): the geoledger's asset, its dated status history, and the theaters whose reports put it there. The server
// builds all three into the place's entity view (backend `views/entity.py`: the theaters come from each event's `via`, "daily:<date>:<theater>", how the claim
// got in, so no extra lookup or guess); a spelling merged into another place has no view of its own and is read from the ledger's stub so the page can
// redirect. Server only.

export type PlaceContext = { asset: GeoAsset; history: GeoEvent[]; theaters: TheaterRef[] };

const HISTORY_MAX = 500;

export async function placeContext(id: string): Promise<PlaceContext | null> {
  const place = (await entityView("place", id))?.place;
  const asset = place ? toAsset(place.asset) : null;
  if (!place || !asset) {
    const stub = await getAsset(id);
    return stub?.merged_into ? { asset: stub, history: [], theaters: [] } : null;
  }
  const history = place.history
    .map(toEvent)
    .filter((e): e is GeoEvent => e !== null)
    .sort((a, b) => a.occurred_on.localeCompare(b.occurred_on) || a.observed_at.localeCompare(b.observed_at))
    .slice(0, HISTORY_MAX);
  return { asset, history, theaters: place.theaters.map(toTheaterRef) };
}

/** Ids of the places worth indexing: those with at least one status event on record. */
export async function indexedPlaceIds(): Promise<string[]> {
  return (await queryAssets({ hasEvents: true, limit: 2000 })).map((a) => a.id);
}
