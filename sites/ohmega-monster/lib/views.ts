import { parseStamp } from "./contract";
import { publishedDoc, TTL } from "./store";
import type { CountryView, DailyHubView, EntityView, EventView, GraphView, HomeView, HudView, SearchIndexView, SeriesIndexView, SituationsView, SituationView } from "./views-types";

export * from "./views-types";

// The reader of the server-built views (docs/architecture/views.md). A page asks for the ONE view it needs, by key; the worker server built it from the
// stores and the corpus index, and published it as `docs/views/<key>.json.gz` next to the other documents, so it travels the same path as every other
// document (lib/store.ts: cached by Next's data cache per window, a missing object is "not published" -> null, any other failure throws so ISR keeps the
// last good page).
//
// There is no file fallback: a view exists only on the server. A page whose view is not published says so (or shows nothing) instead of rebuilding the
// answer from raw documents - that per-request aggregation is what views replaced.
//
// A view whose schema is not one this reader knows is treated as not published, so a newer server can introduce /2 without breaking a site that has not
// caught up. The general gate is lib/contract.ts (inside `publishedDoc`, from the registry-generated lib/contracts.json); the check below is the stricter
// per-family one: a view must also carry its stamp (they always do), and its family must be the one asked for.

const KEY = /^[\w~-]+(?:[./][\w~-]+)*$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const ID = /^[\w.-]+$/;

export type ViewFamily = "country" | "situation" | "situations" | "entity" | "event" | "series" | "series-index" | "home" | "hud" | "daily-hub" | "graph" | "search-index" | "manifest";
type Family = ViewFamily;

/** One view by key ("country/FR", "home"), checked against its family's schema. */
export async function viewDoc<T>(family: Family, key: string, revalidate: number = TTL.daily): Promise<T | null> {
  if (!KEY.test(key) || key.includes("..")) return null;
  const doc = await publishedDoc(`views/${key}.json`, revalidate);
  if (typeof doc !== "object" || doc === null) return null;
  const got = parseStamp((doc as { schema?: unknown }).schema);
  return got !== null && got.id === `ohmega.view.${family}` ? (doc as T) : null; // the major was already judged by the gate in publishedDoc
}

export const countryView = (iso: string): Promise<CountryView | null> => (/^[A-Z]{2}$/.test(iso) ? viewDoc<CountryView>("country", `country/${iso}`) : Promise.resolve(null));

export const situationView = (id: string): Promise<SituationView | null> => (ID.test(id) ? viewDoc<SituationView>("situation", `situation/${id}`) : Promise.resolve(null));

export const situationsView = (): Promise<SituationsView | null> => viewDoc<SituationsView>("situations", "situations");

/** An entity by kind and id as the server keyed it (`entity_key` in views/entity.py: the id without its kind prefix, made path-safe). */
export const entityView = (kind: string, id: string): Promise<EntityView | null> =>
  /^[a-z]+$/.test(kind) && ID.test(id) ? viewDoc<EntityView>("entity", `entity/${kind}/${id}`) : Promise.resolve(null);

export const eventView = (date: string, theater: string): Promise<EventView | null> =>
  DATE.test(date) && ID.test(theater) ? viewDoc<EventView>("event", `event/${date}/${theater}`) : Promise.resolve(null);

export const homeView = (): Promise<HomeView | null> => viewDoc<HomeView>("home", "home", TTL.fast);

export const hudView = (): Promise<HudView | null> => viewDoc<HudView>("hud", "hud", TTL.fast);

export const dailyHubView = (): Promise<DailyHubView | null> => viewDoc<DailyHubView>("daily-hub", "daily-hub", TTL.fast);

export const graphView = (): Promise<GraphView | null> => viewDoc<GraphView>("graph", "graph");

export const searchIndex = (): Promise<SearchIndexView | null> => viewDoc<SearchIndexView>("search-index", "search-index", TTL.static);

export const seriesIndex = (): Promise<SeriesIndexView | null> => viewDoc<SeriesIndexView>("series-index", "series-index", TTL.static);

/** Any view by its key and family, for the agent API (which serves them with their provenance). */
export const anyView = <T>(family: Family, key: string): Promise<T | null> => viewDoc<T>(family, key);
