import { cache } from "react";

import { allActors, type Actor } from "./actors";
import { allDailyDates, daily, headlineOf, theaterAnchor, type Daily } from "./daily";
import { dossierList } from "./dossier";
import { buildLinker, type Linker } from "./countries";
import { countryName } from "./flags";
import { maxBand, type Band, type Direction } from "./intel";
import { recordLedger } from "./record";
import type { OnRecord } from "./record-model";

// The entity graph, derived (no model calls, no new documents): countries (actors) and theaters are the
// first two object types, and every link between them is computed here from what is already published:
// the actors feed (who a profile says it is involved in), the dossier index (a theater's state), the
// recent daily reports (who the pulses and developments name) and the statements ledger. Pages render
// the result and link only what exists. Server only (reads documents).

const DAILY_DOMAIN = "geopolitics";
const DAILIES_READ = 3; // recent reports mined for developments and co-occurrence
const DEVELOPMENTS_SHOWN = 6;
const SAID_SHOWN = 5;

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

const DIRECTION_RANK: Record<Direction, number> = { rising: 0, unclear: 2, steady: 1, easing: 3 };
const norm = (s: string) => s.trim().toLowerCase();

export type Index = {
  actors: Map<string, Actor>;
  refs: Map<string, TheaterRef>;
  dailies: Daily[];
  /** theater id -> iso2 -> how strongly the sources tie them (profile mentions, pulses, numbers, developments). */
  ties: Map<string, Map<string, number>>;
};

function tie(ties: Index["ties"], theater: string, iso: string, w: number) {
  if (!theater || !/^[A-Z]{2}$/.test(iso)) return;
  const m = ties.get(theater) ?? new Map<string, number>();
  m.set(iso, (m.get(iso) ?? 0) + w);
  ties.set(theater, m);
}

/** One load per request of everything the links are computed from. */
export const entityIndex = cache(async (): Promise<Index> => {
  const [actorList, items, dates] = await Promise.all([allActors(), dossierList(), allDailyDates(DAILY_DOMAIN)]);
  const dailies = (await Promise.all(dates.slice(0, DAILIES_READ).map((d) => daily(DAILY_DOMAIN, d)))).filter((d): d is Daily => d !== null);
  const refs = new Map<string, TheaterRef>();
  for (const i of items) if (!i.merged_into) refs.set(i.theater_id, { id: i.theater_id, name: i.name, direction: i.escalation_direction, band: i.max_band, linked: true });
  // A theater in a recent report but without a dossier is still a theater: named, not linked.
  for (const d of dailies)
    for (const t of d.theaters) if (!refs.has(t.theater_id)) refs.set(t.theater_id, { id: t.theater_id, name: t.name, direction: t.escalation.direction, band: maxBand(t.pulses), linked: false });

  const actors = new Map(actorList.map((a) => [a.iso2, a]));
  const ties: Index["ties"] = new Map();
  for (const a of actorList) for (const t of a.involved.theaters) tie(ties, t.id, a.iso2, Math.max(1, t.mentions));
  for (const d of dailies)
    for (const t of d.theaters) {
      for (const p of t.pulses) for (const iso of p.actors_iso2) tie(ties, t.theater_id, iso, 1);
      for (const a of t.numbers?.actors ?? []) tie(ties, t.theater_id, a.iso2.toUpperCase(), 1);
    }
  return { actors, refs, dailies, ties };
});

const refOf = (idx: Index, id: string, fallbackName = ""): TheaterRef =>
  idx.refs.get(id) ?? { id, name: fallbackName || id, direction: "unclear", band: "unassessed", linked: false };

/** Moving theaters first (rising, then steady, easing), then by how often the actor is named. */
const bySalience = (a: InvolvedTheater, b: InvolvedTheater) =>
  DIRECTION_RANK[a.direction] - DIRECTION_RANK[b.direction] || b.mentions - a.mentions || a.name.localeCompare(b.name);

/** The display name for a country code: the profile's name when there is one. */
export const actorName = (idx: Pick<Index, "actors">, iso: string): string => idx.actors.get(iso)?.name ?? countryName(iso);

function developmentsFor(idx: Index, iso: string): Development[] {
  const name = norm(countryName(iso));
  const named = (s: string) => norm(s) === name || s.trim().toUpperCase() === iso;
  const out: Development[] = [];
  for (const d of idx.dailies)
    d.theaters.forEach((t, i) => {
      const unique = d.theaters.filter((o) => o.theater_id === t.theater_id).length === 1;
      t.developments.forEach((dev, n) => {
        if (!dev.actors.some(named) && !(dev.place && named(dev.place.country))) return;
        out.push({
          date: d.date,
          theater: t.name,
          theaterId: t.theater_id,
          headline: headlineOf(dev.headline, dev.detail, 150) || dev.headline,
          when: dev.when,
          href: `/daily/geopolitics/${d.date}#${theaterAnchor(t, i)}`,
          event: unique ? eventPath(d.date, t.theater_id, n) : "",
        });
      });
    });
  return out.sort((a, b) => b.date.localeCompare(a.date)).slice(0, DEVELOPMENTS_SHOWN);
}

/** Everything that connects one country to the rest of the graph. `null` when nothing does (so a stray
 *  code never becomes an empty page). `profile` is whether the actors feed has the country. */
export async function actorContext(iso: string): Promise<(ActorContext & { profile: boolean }) | null> {
  const idx = await entityIndex();
  const profile = idx.actors.get(iso);
  const mentions = new Map<string, number>();
  for (const [theater, m] of Array.from(idx.ties)) if (m.has(iso)) mentions.set(theater, m.get(iso) ?? 0);

  const theaters = Array.from(mentions, ([id, n]) => ({ ...refOf(idx, id, profile?.involved.theaters.find((t) => t.id === id)?.name), mentions: n })).sort(bySalience);
  const ledger = await recordLedger();
  const all = ledger?.statements ?? [];
  const said = all.filter((s) => s.iso2 === iso).slice(0, SAID_SHOWN);
  const saidAbout = all.filter((s) => s.about_iso2.includes(iso)).length;
  const developments = developmentsFor(idx, iso);

  if (!profile && theaters.length === 0 && said.length === 0 && saidAbout === 0 && developments.length === 0) return null;

  // Relationships: states that share a theater with this one, labelled by the theaters they share.
  const rel = new Map<string, { id: string; name: string }[]>();
  for (const t of theaters) for (const other of Array.from(idx.ties.get(t.id)?.keys() ?? [])) if (other !== iso) rel.set(other, [...(rel.get(other) ?? []), { id: t.id, name: t.name }]);
  const related = Array.from(rel, ([code, via]) => ({ iso2: code, name: actorName(idx, code), via }))
    .sort((a, b) => b.via.length - a.via.length || a.name.localeCompare(b.name));

  return { name: actorName(idx, iso), profile: !!profile, theaters, said, saidAbout, developments, related };
}

/** Theaters that share states with this one, most in common first, each with the shared states. */
export async function relatedTheaters(theaterId: string): Promise<RelatedTheater[]> {
  const idx = await entityIndex();
  const mine = idx.ties.get(theaterId);
  if (!mine) return [];
  const out: RelatedTheater[] = [];
  for (const [id, m] of Array.from(idx.ties)) {
    if (id === theaterId || !idx.refs.get(id)?.linked) continue;
    const shared = Array.from(m.keys()).filter((iso) => mine.has(iso));
    if (shared.length > 0) out.push({ ...refOf(idx, id), shared: shared.map((iso) => ({ iso2: iso, name: actorName(idx, iso) })) });
  }
  return out.sort((a, b) => b.shared.length - a.shared.length || DIRECTION_RANK[a.direction] - DIRECTION_RANK[b.direction] || a.name.localeCompare(b.name));
}

/** The page of one development: the day, the theater and its 1-based position in that theater's section. */
export const eventPath = (date: string, theaterId: string, index: number): string => `/intel/events/${date}/${theaterId}/${index + 1}`;

/** A theater by id: from the dossier index, else as a recent report named it (not linked). */
export async function theaterRef(id: string): Promise<TheaterRef> {
  return refOf(await entityIndex(), id);
}

/** Every state that has a page worth landing on: a profile, or a place in some theater. */
export const linkableActors = cache(async (): Promise<ReadonlySet<string>> => {
  const idx = await entityIndex();
  const out = new Set(idx.actors.keys());
  for (const m of Array.from(idx.ties.values())) for (const iso of Array.from(m.keys())) out.add(iso);
  return out;
});

/** The matcher that turns country names in prose into links (one build per request). */
export const textLinker = cache(async (): Promise<Linker | null> => buildLinker(await linkableActors()));

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

/** The states a theater involves (profiled or not), most tied first. */
export async function theaterStates(theaterId: string): Promise<ActorRef[]> {
  const idx = await entityIndex();
  const m = idx.ties.get(theaterId);
  if (!m) return [];
  return Array.from(m, ([iso, w]) => ({ iso2: iso, name: actorName(idx, iso), w }))
    .sort((a, b) => b.w - a.w || a.name.localeCompare(b.name))
    .map(({ iso2, name }) => ({ iso2, name }));
}
