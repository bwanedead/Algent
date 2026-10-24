import { anyView, searchIndex, seriesIndex, type CountryView, type EntityView, type SeriesView, type SituationView, type ViewEnvelope, type ViewFamily } from "@/lib/views";

import { apiUrl } from "./ops-desk";
import { abs, badRequest, limitParam, notFound, paginate, sinceParam, str, type ApiResult, type Args, type Obj } from "./util";

// The corpus-backed tools of the agent API: entity(name), about(entity, since, kinds), timeline(entity), related(entity), series(metric) and the corpus half of
// search(q). The corpus is one SQLite index on the worker server, and Vercel cannot open it, so the server PRECOMPUTES what these tools answer from: one view per
// entity (documents, claims with their sources, events, typed relations, series), one per country and situation, one per metric, and a compact search index of
// names and titles (backend `views/`, docs/architecture/views.md "Agent endpoints"). These ops read those files; nothing here queries a database or aggregates
// raw documents. Every result carries the view's provenance (which products and documents it was derived from), each record keeps its own `product`, `origin`
// and source URLs, and every series its `basis` (the stats-registry vocabulary: official, our_count, our_derived, model, reported ...).
//
// Limits, stated so an agent can reason about them: a view holds the NEWEST material (an entity view: 15 documents, 10 claims, 15 events, 12 series), so `about`
// with a `since` older than that returns what the view holds and says so; search covers names, aliases and titles, never document bodies.

const DOC_SECTIONS = ["document", "claim", "event"] as const;

// ---- resolving a name ---------------------------------------------------------------------------------------------

/** The comparison form of a name: the same rule the server's corpus uses (backend corpus/norm.py): accents stripped, case folded, punctuation to single spaces. */
export const norm = (s: string): string =>
  s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/’/g, "'").replace(/[^a-z0-9]+/g, " ").trim();

export type Match = { name: string; kind: string; key: string; uses: number };
type Row = Match & { aliases: string[] };

const TIER: Record<string, number> = { country: 0, actor: 2 };
const tier = (kind: string): number => TIER[kind] ?? 1;

async function rows(): Promise<{ rows: Row[]; as_of: string; total: number }> {
  const idx = await searchIndex();
  if (!idx) throw notFound("the entity index (not published yet)");
  return {
    rows: idx.entities.map(([name, kind, key, uses, aliases]) => ({ name, kind, key, uses, aliases })),
    as_of: idx.as_of,
    total: idx.entities_total,
  };
}

const view = (key: string): { family: ViewFamily; key: string } => {
  const head = key.split("/", 1)[0];
  return { family: head === "country" ? "country" : head === "situation" ? "situation" : "entity", key };
};

/** The entity a name means. Exact name or alias first (a country beats a same-named thing, then the most-mentioned wins); else names that contain it. The others are
 *  returned so the caller can say the name was ambiguous - the API never silently picks between two kinds of thing. */
export async function resolveEntity(a: Args, param = "entity"): Promise<{ best: Match; alternatives: Match[] }> {
  const wanted = a.key || "";
  const name = a[param] || a.name || "";
  const idx = await rows();
  if (wanted) {
    const hit = idx.rows.find((r) => r.key === wanted);
    if (hit) return { best: hit, alternatives: [] };
    if (!/^(country|situation|entity)\//.test(wanted)) throw badRequest("key must be a view key from a previous result, e.g. entity/org/nato or country/FR");
    return { best: { name: wanted, kind: wanted.split("/")[0] === "entity" ? wanted.split("/")[1] : wanted.split("/")[0], key: wanted, uses: 0 }, alternatives: [] };
  }
  const q = norm(name);
  if (q.length < 2) throw badRequest(`${param} must be a name of at least 2 characters (or pass key=<view key> from a previous result)`);
  const exact = idx.rows.filter((r) => norm(r.name) === q || r.aliases.some((x) => norm(x) === q));
  const pool = exact.length > 0 ? exact : idx.rows.filter((r) => norm(r.name).includes(q) || r.aliases.some((x) => norm(x).includes(q)));
  if (pool.length === 0) throw notFound(`entity "${name}" (the index holds ${idx.total} entities with substance; try search?q=${encodeURIComponent(name)})`);
  const ranked = [...pool].sort((x, y) => tier(x.kind) - tier(y.kind) || y.uses - x.uses || x.name.length - y.name.length || x.key.localeCompare(y.key));
  const out = ranked.map((r): Match => ({ name: r.name, kind: r.kind, key: r.key, uses: r.uses }));
  return { best: out[0], alternatives: out.slice(1, 6) };
}

type Loaded = { match: Match; env: ViewEnvelope; body: Obj; alternatives: Match[] };

async function load(a: Args, param = "entity"): Promise<Loaded> {
  const { best, alternatives } = await resolveEntity(a, param);
  const v = view(best.key);
  const body = await anyView<Obj & ViewEnvelope>(v.family, v.key);
  if (!body) throw notFound(`the view of ${best.name} (${best.key}) is not published`);
  return { match: best, env: body, body, alternatives };
}

const citeOf = (m: Match, body: Obj): string => {
  if (m.key.startsWith("country/")) return abs(`/intel/actors/${m.key.slice(8)}`);
  if (m.key.startsWith("situation/")) return abs(`/situations/${m.key.slice(10)}`);
  const id = str(body.id);
  if (id.startsWith("asset:")) return abs(`/intel/places/${id.slice(6)}`);
  const doc = Array.isArray(body.documents) ? (body.documents as Obj[]).find((d) => str(d.url).startsWith("/")) : undefined;
  return doc ? abs(str(doc.url)) : abs("/");
};

const resultOf = (l: Loaded, data: unknown, extra: Partial<ApiResult> = {}): ApiResult => ({
  data,
  as_of: l.env.as_of || null,
  cite_as: citeOf(l.match, l.body),
  source: l.env.schema,
  provenance: l.env.provenance,
  ...extra,
});

/** The distinct `basis` values in a result, so a consumer sees at a glance which kinds of number it holds. */
export function basesOf(data: unknown, found = new Set<string>()): string[] {
  if (Array.isArray(data)) data.forEach((x) => basesOf(x, found));
  else if (typeof data === "object" && data !== null) {
    for (const [k, v] of Object.entries(data)) {
      if (k === "basis" && typeof v === "string" && v) found.add(v);
      else basesOf(v, found);
    }
  }
  return Array.from(found).sort();
}

const matchOut = (m: Match) => ({ name: m.name, kind: m.kind, key: m.key, uses: m.uses });

// ---- shapes by family ---------------------------------------------------------------------------------------------

type Item = { date: string; type: "document" | "claim" | "event"; kind: string; id: string; title: string; detail?: string; status?: string; url?: string; sources: string[]; product: string; origin: string; [k: string]: unknown };

const day = (s: unknown): string => str(s).slice(0, 10);
const list = (v: unknown): Obj[] => (Array.isArray(v) ? (v as Obj[]).filter((x) => typeof x === "object" && x !== null) : []);
const srcs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && x !== "") : []);

/** The material a view holds about its subject, as uniform items: documents, claims and events with provenance and source URLs. */
function itemsOf(body: Obj, family: string): { documents: Item[]; claims: Item[]; events: Item[]; note: string } {
  if (family === "entity") {
    return {
      documents: list(body.documents).map((d): Item => ({ date: day(d.date), type: "document", kind: str(d.kind), id: str(d.id), title: str(d.title), status: str(d.status), url: str(d.url), sources: srcs(d.sources), product: str(d.product), origin: str(d.origin) })),
      claims: list(body.claims).map((c): Item => ({ date: day(c.at), type: "claim", kind: "claim", id: str(c.id), title: str(c.text), status: str(c.status), grounding: str(c.grounding), confidence: str(c.confidence), sources: list(c.sources).map((s) => str(s.url)), product: str(c.product), origin: str(c.origin) })),
      events: list(body.events).map((e): Item => ({ date: day(e.date), type: "event", kind: str(e.kind), id: str(e.id), title: str(e.title), detail: str(e.detail), status: str(e.status), url: str(e.url), sources: srcs(e.sources), product: str(e.product), origin: str(e.origin) })),
      note: "An entity view holds the newest 15 documents, 10 claims and 15 events about it.",
    };
  }
  if (family === "country") {
    const panel = (body.panel ?? {}) as Obj;
    const ctx = (body.context ?? {}) as Obj;
    return {
      documents: list(panel.briefs).map((b): Item => ({ date: day(b.date), type: "document", kind: str(b.kind), id: str(b.href), title: str(b.text), url: str(b.href), sources: [], product: "dailies", origin: str(b.href), theme: str(b.theme) })),
      claims: [],
      events: [
        ...list(ctx.developments).map((d): Item => ({ date: day(d.date), type: "event", kind: "development", id: str(d.href), title: str(d.headline), detail: str(d.detail), url: str(d.href), sources: [], product: "dailies", origin: str(d.href) })),
        ...list(body.sanctions).map((s): Item => ({ date: day(s.on_date), type: "event", kind: `sanction_${str(s.action)}`, id: str(s.id), title: `${str(s.name)} (${str(s.type)})`, url: str(s.source_url), sources: srcs([s.source_url]), product: "sanctions", origin: str(s.source) })),
        ...list(body.calendar).map((c): Item => ({ date: day(c.on_date), type: "event", kind: `calendar_${str(c.kind)}`, id: str(c.id), title: str(c.title), url: str(c.source_url), sources: srcs([c.source_url]), product: "calendar", origin: str(c.source) })),
      ],
      note: "A country view holds the newest 120 brief lines naming it, its last developments, 50 sanctions rows and the calendar ahead.",
    };
  }
  const stream = (body.stream ?? {}) as Obj;
  return {
    documents: [...list(stream.full), ...list(stream.index)].map((e): Item => ({ date: day(e.date), type: "document", kind: "daily", id: str(e.href), title: str(e.headline), url: str(e.href), sources: [], product: "dailies", origin: str(e.href), desk: str(e.desk) })),
    claims: [],
    events: [],
    note: "A situation view lists every Daily section about it (the newest as full sections on the site, the rest as index rows).",
  };
}

const wantSections = (kinds: Set<string>) => {
  const sections = new Set<string>(DOC_SECTIONS.filter((s) => kinds.has(s)));
  const rest = new Set(Array.from(kinds).filter((k) => !(DOC_SECTIONS as readonly string[]).includes(k)));
  const section = (s: string) => sections.size === 0 || sections.has(s);
  return { section, rest };
};

function kindsParam(v: string | undefined): Set<string> {
  const out = new Set<string>();
  for (const k of (v ?? "").split(",")) {
    const t = k.trim().toLowerCase();
    if (t) out.add(t);
  }
  if (out.size > 12) throw badRequest("kinds takes at most 12 comma-separated values");
  return out;
}

// ---- the ops ------------------------------------------------------------------------------------------------------

/** entity(name): who or what it is, with its aliases, counts, latest status, typed relations, top related, series and the newest few documents, claims and events. */
export async function entityOp(a: Args): Promise<ApiResult> {
  const l = await load({ ...a, entity: a.name || a.entity });
  const family = view(l.match.key).family;
  const b = l.body;
  let data: Obj;
  if (family === "entity") {
    const items = itemsOf(b, "entity");
    data = {
      ...(Object.fromEntries(["id", "kind", "name", "aliases", "iso2", "lat", "lon", "attrs", "also_known_as_ids", "uses", "counts", "latest", "situations", "relations"].map((k) => [k, b[k]])) as Obj),
      related: list(b.related).slice(0, 8),
      series: list(b.series).map((s) => ({ ...s, points: undefined })),
      recent: { documents: items.documents.slice(0, 5), claims: items.claims.slice(0, 5), events: items.events.slice(0, 5) },
      ...(b.place ? { place: b.place } : {}),
    };
  } else if (family === "country") {
    const panel = (b.panel ?? {}) as Obj;
    data = {
      id: `country:${str(b.iso)}`, kind: "country", iso2: b.iso, name: b.name, region: b.region, capital: b.capital, profiled: b.profiled, leaders: panel.leaders, stats: panel.stats, counts: panel.counts,
      grid: panel.grid, theaters: list((b.context as Obj | undefined)?.theaters).slice(0, 8), relations: b.relations ?? [], series: list(b.series).map((s) => ({ ...s, points: undefined })),
      recent: { briefs: list(panel.briefs).slice(0, 8), developments: list((b.context as Obj | undefined)?.developments), sanctions: list(b.sanctions).slice(0, 5), calendar: list(b.calendar).slice(0, 5) },
    };
  } else {
    const items = itemsOf(b, "situation");
    data = { ...(Object.fromEntries(["id", "name", "desk", "domain", "states", "related", "pulses", "briefs", "current", "places", "map_points"].map((k) => [k, b[k]])) as Obj), kind: "situation", days: (b.stream as Obj | undefined)?.days_total, recent: { documents: items.documents.slice(0, 8) } };
  }
  const out = { match: matchOut(l.match), alternatives: l.alternatives.map(matchOut), entity: data, more: { about: apiUrl(`/about?key=${encodeURIComponent(l.match.key)}`), timeline: apiUrl(`/timeline?key=${encodeURIComponent(l.match.key)}`), related: apiUrl(`/related?key=${encodeURIComponent(l.match.key)}`), series: apiUrl(`/series?key=${encodeURIComponent(l.match.key)}`) } };
  return resultOf(l, out, {
    basis: basesOf(out),
    note: l.alternatives.length > 0 ? `"${str(a.name || a.entity)}" matched ${l.alternatives.length + 1} entities; the first is returned. Pass key=<alternatives[].key> for another.` : "Claims are graded statements with their sources; a statement proves it was said, not that it is true.",
  });
}

/** about(entity, since, kinds): everything the view holds about the entity since a date, newest first, each item with its product, origin and source URLs. */
export async function aboutOp(a: Args): Promise<ApiResult> {
  const l = await load(a);
  const since = sinceParam(a.since).slice(0, 10);
  const kinds = kindsParam(a.kinds);
  const { section, rest } = wantSections(kinds);
  const items = itemsOf(l.body, view(l.match.key).family);
  const keep = (xs: Item[]) => xs.filter((i) => (!since || i.date >= since) && (rest.size === 0 || rest.has(i.kind.toLowerCase()))).sort((x, y) => y.date.localeCompare(x.date) || x.id.localeCompare(y.id));
  const limit = limitParam(a.limit, 30);
  const out = {
    entity: matchOut(l.match),
    since: since || null,
    documents: section("document") ? keep(items.documents).slice(0, limit) : [],
    claims: section("claim") && rest.size === 0 ? keep(items.claims).slice(0, limit) : [],
    events: section("event") ? keep(items.events).slice(0, limit) : [],
  };
  const oldest = [...items.documents, ...items.claims, ...items.events].map((i) => i.date).filter(Boolean).sort()[0] ?? "";
  return resultOf(l, out, {
    basis: basesOf(out),
    note: `${items.note}${since && oldest && since < oldest ? ` Nothing older than ${oldest} is held, so a since of ${since} is answered from ${oldest}.` : ""}`,
  });
}

/** timeline(entity): documents and events about the entity in date order (oldest first), a development repeated in several reports once. */
export async function timelineOp(a: Args): Promise<ApiResult> {
  const l = await load(a);
  const since = sinceParam(a.since).slice(0, 10);
  const items = itemsOf(l.body, view(l.match.key).family);
  const seen = new Set<string>();
  const rows = [...items.documents, ...items.events]
    .filter((i) => i.date && (!since || i.date >= since))
    .sort((x, y) => x.date.localeCompare(y.date) || x.type.localeCompare(y.type) || x.id.localeCompare(y.id))
    .filter((i) => {
      const k = `${i.date}|${i.type}|${i.title}`;
      return seen.has(k) ? false : (seen.add(k), true);
    });
  const limit = limitParam(a.limit, 50);
  const out = { entity: matchOut(l.match), timeline: rows.slice(-limit), total: rows.length };
  return resultOf(l, out, { basis: basesOf(out), note: items.note });
}

/** related(entity): what it is most connected to and why (typed edges, shared claims, events and documents), with the parts shown. */
export async function relatedOp(a: Args): Promise<ApiResult> {
  const l = await load(a);
  const kinds = kindsParam(a.kinds);
  const family = view(l.match.key).family;
  const b = l.body;
  const ctx = (b.context ?? {}) as Obj;
  const related =
    family === "entity"
      ? list(b.related)
      : family === "country"
        ? list(ctx.related).map((r) => ({ entity: `country:${str(r.iso2)}`, name: str(r.name), kind: "country", score: list(r.via).length, via: { theaters: list(r.via).length }, shared_theaters: r.via }))
        : list(b.related).map((r) => ({ entity: str(r.id), name: str(r.name), kind: "situation", score: list(r.shared).length, via: { states: list(r.shared).length }, shared_states: r.shared }));
  const relations = family === "entity" || family === "country" ? list(b.relations) : [];
  const out = {
    entity: matchOut(l.match),
    related: related.filter((r) => kinds.size === 0 || kinds.has(str(r.kind))).slice(0, limitParam(a.limit, 15)),
    relations,
  };
  return resultOf(l, out, { basis: basesOf(out), note: "score = typed edges x3 + shared claims x2 + shared events x1.5 + shared documents x1 (countries: theaters shared; situations: states shared). `relations` are the typed edges with their evidence." });
}

const metricKey = (metric: string): string => `series/${metric.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^_+|_+$/g, "") || "x"}`;

/** series(metric): a measured series across the entities that have it, or (with an entity) that entity's own series; each with unit and basis. */
export async function seriesOp(a: Args): Promise<ApiResult> {
  const since = /^\d{4}$/.test(a.since ?? "") ? (a.since as string) : sinceParam(a.since).slice(0, 10); // a year is a fine start for a yearly indicator
  const metric = (a.metric || "").trim();
  const trim = (pts: [string, number][]) => (since ? pts.filter((p) => p[0] >= since) : pts);
  if (a.entity || a.key) {
    const l = await load(a);
    const own = list(l.body.series).filter((s) => !metric || str(s.metric) === metric || (/[.*]$/.test(metric) && str(s.metric).startsWith(metric.replace(/\*$/, ""))));
    const out = { entity: matchOut(l.match), series: own.map((s) => ({ ...s, points: trim((s.points as [string, number][]) ?? []) })) };
    return resultOf(l, out, { basis: basesOf(out), note: "Each series states its basis: official (published by the body that measures it), our_count (a minimum, from our receivers), our_derived (our computation), model (a model's reading), reported (a figure a source cited)." });
  }
  if (metric.length < 2) throw badRequest("give a metric (e.g. gdp, chk_hormuz_transits; a trailing . or * lists a family) or an entity");
  const [idx, exact] = await Promise.all([seriesIndex(), anyView<SeriesView>("series", metricKey(metric))]);
  if (exact) {
    const out = { ...exact, entities: exact.entities.map((e) => ({ ...e, points: trim(e.points) })) };
    return { data: out, as_of: exact.as_of || null, cite_as: abs("/explore"), source: exact.schema, provenance: exact.provenance, basis: [exact.basis].filter(Boolean), note: `${exact.entities.length} of ${exact.entities_total} entities shown, the most recently updated first; the entity's own view has the rest.` };
  }
  if (!idx) throw notFound("the series index (not published yet)");
  const q = norm(metric.replace(/[.*]+$/, ""));
  const prefix = /[.*]$/.test(metric);
  const found = idx.metrics.filter((m) => (prefix ? m.metric.startsWith(metric.replace(/\*$/, "")) : norm(m.metric).includes(q) || norm(m.label).includes(q)));
  if (found.length === 0) throw notFound(`metric "${metric}" (the index lists ${idx.metrics_total} metrics; try a part of its name)`);
  const p = paginate(found, limitParam(a.limit, 30), a.cursor);
  return {
    data: { metric: metric, candidates: p.items, total: p.total },
    as_of: idx.as_of || null,
    cite_as: abs("/explore"),
    source: idx.schema,
    provenance: idx.provenance,
    basis: Array.from(new Set(p.items.map((m) => m.basis).filter(Boolean))).sort(),
    next_cursor: p.next_cursor,
    note: "No metric has exactly this name: these match it. Ask series again with one metric id for its values.",
  };
}

// ---- the corpus half of search --------------------------------------------------------------------------------------

export type CorpusHit = { type: "entity" | "document"; id: string; title: string; text: string; date: string; cite_as: string; api_url: string };

/** Entities (by name and alias) and document titles from the search index, in the shape the site-wide search ranks. Empty when the index is not published. */
export async function corpusHits(): Promise<CorpusHit[]> {
  const idx = await searchIndex();
  if (!idx) return [];
  const out: CorpusHit[] = [];
  for (const [name, kind, key, , aliases] of idx.entities) {
    const cite = key.startsWith("country/") ? `/intel/actors/${key.slice(8)}` : key.startsWith("situation/") ? `/situations/${key.slice(10)}` : "/";
    out.push({ type: "entity", id: key, title: name, text: `${kind} ${aliases.join(" ")}`, date: "", cite_as: abs(cite), api_url: apiUrl(`/entity?key=${encodeURIComponent(key)}`) });
  }
  for (const [id, date, kind, title, url] of idx.documents) {
    out.push({ type: "document", id, title, text: kind, date, cite_as: abs(url || "/"), api_url: "" });
  }
  return out;
}
