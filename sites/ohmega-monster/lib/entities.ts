import { cache } from "react";

import { headlineOf } from "./daily";
import { buildLinker, type Linker } from "./countries";
import { countryName } from "./flags";
import type { Band, Direction } from "./intel";
import { parseOnRecord, type OnRecord } from "./record-model";
import { countryView, graphView, type TheaterRefView } from "./views";

// The entity graph (no model calls, no new documents): countries (actors) and theaters are the first two object types, and every link between them is
// computed by the worker server from what is published (backend `views/graph.py` and `views/country.py`) and read here from two small views: the shared
// theater-state graph (which theaters and states have a page, how strongly the sources tie them) and, per state, its context. Pages render the result
// and link only what exists. Server only (reads documents).

export type TheaterRef = {
  id: string;
  name: string;
  direction: Direction;
  band: Band;
  /** True when the theater has a dossier page to link to. */
  linked: boolean;
};
export type InvolvedTheater = TheaterRef & { mentions: number };
export type ActorRef = { iso2: string; name: string };
export type RelatedActor = ActorRef & { via: { id: string; name: string }[] };
export type RelatedTheater = TheaterRef & { shared: ActorRef[] };
export type Development = { date: string; theater: string; theaterId: string; headline: string; when: string; href: string; /** The development's own page; "" when the day has the theater twice. */ event: string };
export type ActorContext = {
  name: string;
  theaters: InvolvedTheater[];
  /** Statements by this state's officials, newest first (the ledger window). */
  said: OnRecord[];
  /** How many statements in the ledger are about this state. */
  saidAbout: number;
  developments: Development[];
  related: RelatedActor[];
};

const DIRECTIONS: readonly Direction[] = ["rising", "steady", "easing", "unclear"];
const BANDS: readonly Band[] = ["calm", "elevated", "severe", "critical", "unassessed"];

const direction = (v: string): Direction => (DIRECTIONS as readonly string[]).includes(v) ? (v as Direction) : "unclear";
const band = (v: string): Band => ((BANDS as readonly string[]).includes(v) ? (v as Band) : "unassessed");

/** A theater ref as a view carries it (free words from JSON) turned into the typed ref the components take. */
export const toTheaterRef = (t: TheaterRefView): TheaterRef => ({ id: t.id, name: t.name, direction: direction(t.direction), band: band(t.band), linked: t.linked });

export type Index = {
  /** Profiled states' names by ISO code (a state without a profile is named by `countryName`). */
  names: ReadonlyMap<string, string>;
  refs: Map<string, TheaterRef>;
  /** theater id -> iso2 -> how strongly the sources tie them (profile mentions, pulses, numbers). */
  ties: Map<string, Map<string, number>>;
  /** Every state that has a page worth landing on: a profile, or a place in some theater. */
  linkable: ReadonlySet<string>;
};

/** One load per request of the graph view (a few KB) - everything the links are computed from. A missing view is an empty graph: nothing links. */
export const entityIndex = cache(async (): Promise<Index> => {
  const g = await graphView();
  const refs = new Map<string, TheaterRef>();
  for (const t of g?.theaters ?? []) refs.set(t.id, toTheaterRef(t));
  const ties: Index["ties"] = new Map(Object.entries(g?.ties ?? {}).map(([theater, m]) => [theater, new Map(Object.entries(m))]));
  return { names: new Map(Object.entries(g?.names ?? {})), refs, ties, linkable: new Set(g?.linkable ?? []) };
});

const refOf = (idx: Index, id: string, fallbackName = ""): TheaterRef =>
  idx.refs.get(id) ?? { id, name: fallbackName || id, direction: "unclear", band: "unassessed", linked: false };

/** The display name for a country code: the profile's name when there is one. */
export const actorName = (idx: Pick<Index, "names">, iso: string): string => idx.names.get(iso) ?? countryName(iso);

/** Everything that connects one country to the rest of the graph, from its country view. `null` when nothing does (so a stray code never becomes an empty
 *  page). `profile` is whether the actors feed has the country. */
export async function actorContext(iso: string): Promise<(ActorContext & { profile: boolean }) | null> {
  const v = await countryView(iso);
  if (!v) return null;
  const c = v.context;
  const theaters = c.theaters.map((t): InvolvedTheater => ({ ...toTheaterRef(t), mentions: t.mentions }));
  const said = parseOnRecord(c.said);
  const developments = c.developments.map((d): Development => ({ date: d.date, theater: d.theater, theaterId: d.theaterId, headline: headlineOf(d.headline, d.detail, 150) || d.headline, when: d.when, href: d.href, event: d.event }));
  if (!v.profiled && theaters.length === 0 && said.length === 0 && c.saidAbout === 0 && developments.length === 0) return null;
  return { name: v.name, profile: v.profiled, theaters, said, saidAbout: c.saidAbout, developments, related: c.related };
}

/** The page of one development: the day, the theater and its 1-based position in that theater's section. */
export const eventPath = (date: string, theaterId: string, index: number): string => `/intel/events/${date}/${theaterId}/${index + 1}`;

/** The matcher that turns country names in prose into links (one build per request). */
export const textLinker = cache(async (): Promise<Linker | null> => buildLinker((await entityIndex()).linkable));

export type GraphActor = { iso2: string; name: string; weight: number };
export type GraphTheater = TheaterRef & { weight: number };
export type EntityGraph = { actors: GraphActor[]; theaters: GraphTheater[]; links: { iso2: string; theater: string; w: number }[] };

const GRAPH_THEATERS = 40;
const GRAPH_ACTORS = 70;

/** The actor-theater web for the browser: the busiest theaters and the states most tied to them. */
export async function entityGraph(): Promise<EntityGraph> {
  const idx = await entityIndex();
  const total = (id: string) => Array.from(idx.ties.get(id)?.values() ?? []).reduce((a, b) => a + b, 0);
  const theaters = Array.from(idx.ties.keys())
    .filter((id) => idx.refs.has(id))
    .map((id) => ({ ...refOf(idx, id), weight: total(id) }))
    .sort((a, b) => b.weight - a.weight)
    .slice(0, GRAPH_THEATERS);
  const keep = new Set(theaters.map((t) => t.id));
  const byActor = new Map<string, number>();
  for (const t of theaters) for (const [iso, w] of Array.from(idx.ties.get(t.id) ?? [])) byActor.set(iso, (byActor.get(iso) ?? 0) + w);
  const actors = Array.from(byActor, ([iso2, weight]) => ({ iso2, name: actorName(idx, iso2), weight }))
    .sort((a, b) => b.weight - a.weight)
    .slice(0, GRAPH_ACTORS);
  const shown = new Set(actors.map((a) => a.iso2));
  const links = Array.from(idx.ties).flatMap(([theater, m]) =>
    keep.has(theater) ? Array.from(m).filter(([iso]) => shown.has(iso)).map(([iso2, w]) => ({ iso2, theater, w })) : [],
  );
  return { actors, theaters, links };
}
