// The shapes of the server-built views (backend `algent_backend/views/`, docs/architecture/views.md). Types only, client-safe: the reader is lib/views.ts.
//
// A view is a small JSON document the worker server builds and publishes at `docs/views/<key>.json.gz`; a page reads the ONE it needs. Every view opens
// with the same envelope. Fields that are raw documents (a Daily section, a development, a snapshot) are parsed by the same parsers the site already uses
// for the full documents (parseTheater, parseDevelopment, parseSnapshot, parseDaily), so a view never needs a second reader.

import type { ActorLite } from "./actors";
import type { CalendarRow } from "./calendar-shared";
import type { Direction, Pace } from "./intel";
import type { CountryBrief, GlobeData } from "./globe/data";
import type { HudDaily, HudPulse, HudTheater, HudTrader } from "./globe/hud-data";
import type { SanctionsRow } from "./sanctions-shared";

export type ViewEnvelope = {
  schema: string;
  /** When this CONTENT was first built (an unchanged view keeps it). */
  built_at: string;
  /** Date of the newest input. */
  as_of: string;
  provenance: { builder: string; sources: { product: string; from: string }[] };
};

export type TheaterRefView = { id: string; name: string; direction: Direction; band: string; linked: boolean };
export type ActorRefView = { iso2: string; name: string };

// ---- country ---------------------------------------------------------------------------------------------------------------
/** One stat bar of the globe panel with the raw value: the site words it (`fmt` in lib/actors.ts). `pos` is 0..1 on the log track around the profiled median. */
export type RawPanelStat = { id: string; label: string; value: number; unit: string; year: number; pos: number | null; median: number | null };

export type CountryView = ViewEnvelope & {
  iso: string;
  name: string;
  region: string;
  capital: string;
  /** True when an actor profile (figures) exists for the state. */
  profiled: boolean;
  panel: {
    iso: string;
    stats: RawPanelStat[];
    profiled: number;
    counts: { theaters: number; statements7d: number; sanctions: number; calendar: number; anomalies: number };
    grid: { line: string; asOf: string } | null;
    leaders: { head_of_state: string; head_of_government: string };
    briefs: CountryBrief[];
    briefsTotal: number;
  };
  context: {
    theaters: (TheaterRefView & { mentions: number })[];
    said: unknown[];
    saidAbout: number;
    developments: { date: string; theater: string; theaterId: string; headline: string; detail: string; when: string; href: string; event: string }[];
    related: { iso2: string; name: string; via: { id: string; name: string }[] }[];
  };
  sanctions: SanctionsRow[];
  sanctionsTotal: number;
  calendar: CalendarRow[];
  grid: unknown | null;
  snapshot: unknown | null;
  anomalies: { id: string; sentence: string; direction: string; confidence: number; series: string }[];
  relations?: unknown[];
  series?: unknown[];
  about?: Record<string, number>;
};

// ---- situation -------------------------------------------------------------------------------------------------------------
export type StreamEntry = {
  date: string;
  desk: string;
  anchor: string;
  index: number;
  /** The writer's headline, else the start of the bottom line (cut it with `claimOf`). */
  headline: string;
  direction: Direction;
  pace: Pace;
  visuals: { id: string; kind: string; title: string }[];
  developments: number;
  updates: number;
  href: string;
  edition: string;
  /** True when the theater is one section of that report, so its developments have pages of their own. */
  events: boolean;
  update_tags: string[];
  /** The raw Daily section (parse with `parseTheater`); only the newest days carry it. */
  section?: unknown;
};

export type SituationView = ViewEnvelope & {
  id: string;
  name: string;
  desk: string;
  domain: string;
  stream: { days_total: number; full: StreamEntry[]; index: StreamEntry[]; index_total: number };
  snapshot: unknown | null;
  involved: ActorLite[];
  states: ActorRefView[];
  related: (TheaterRefView & { shared: ActorRefView[] })[];
};

export type SituationsView = ViewEnvelope & {
  desks: { desk: string; active: SituationRowView[]; quiet: SituationRowView[]; merged: SituationRowView[] }[];
};
export type SituationRowView = { item: Record<string, unknown>; dossier: { escalation_history: unknown[]; coverage_series: unknown[] } };

// ---- entity, event ---------------------------------------------------------------------------------------------------------
export type EntityView = ViewEnvelope & {
  id: string;
  kind: string;
  name: string;
  aliases: string[];
  iso2: string | null;
  lat: number | null;
  lon: number | null;
  attrs: Record<string, unknown>;
  also_known_as_ids: string[];
  uses: number;
  counts: { documents: number; claims: number; events: number; series: number };
  latest: Record<string, unknown>;
  situations: { entity: string; name: string; shared: number }[];
  relations: { rel: string; direction: string; entity: string; name: string; kind: string; count: number; latest: string; earliest: string; evidence: string; note: string }[];
  related: { entity: string; name: string; kind: string; score: number; via: Record<string, number> }[];
  documents: EntityDocument[];
  claims: EntityClaim[];
  events: EntityEvent[];
  series: EntitySeries[];
  /** A geoledger place only: the asset row, its status history and the theaters whose reports put it there. */
  place?: { asset: Record<string, unknown>; history: Record<string, unknown>[]; theaters: TheaterRefView[] };
};
export type EntityDocument = { id: string; kind: string; domain: string; date: string; title: string; url: string; status: string; product: string; origin: string; roles: string; sources: string[] };
export type EntityClaim = {
  id: string; text: string; status: string; grounding: string; confidence: string; document_id: string; at: string; product: string; origin: string;
  sources: { url: string; title: string; domain: string; relation: string }[];
};
export type EntityEvent = { id: string; kind: string; date: string; end_date: string; title: string; detail: string; status: string; place: string; document_id: string; url: string; product: string; origin: string; sources: string[] };
export type EntitySeries = { metric: string; label: string; unit: string; basis: string; n: number; first: string; last: string; product: string; points: [string, number][]; latest: { ts: string; value: number; source: string } | null };

export type EventView = ViewEnvelope & {
  date: string;
  theater: TheaterRefView;
  name: string;
  anchor: string;
  index: number;
  domain: string;
  /** The section's developments, raw (parse each with `parseDevelopment`). */
  developments: unknown[];
  /** For each development, the state each named actor resolves to (null: not a state). */
  actor_isos: (string | null)[][];
};

// ---- home, hud, daily hub, graph, search -----------------------------------------------------------------------------------
export type HomeView = ViewEnvelope & {
  /** Each desk's newest report as a digest (parse with `parseDaily`). */
  reports: Record<string, unknown | null>;
  snapshot: unknown | null;
  moving: { id: string; name: string; desk: string; stamp: string }[];
  coming: CalendarRow[];
  facts: {
    daily_stamp: string;
    situations: { active: number; rising: number; stamp: string };
    actors: number;
    record: { count: number; shown: number; total: number | null; window_days: number | null; as_of: string } | null;
    pulses: { total: number; severe: number; built_at: string };
    calendar_30d: number;
    sanctions: { additions: number; newest_observed: string };
  };
};

/** `HudData` without its live block and with raw rows where the site words them: the site maps it (lib/globe-hud.ts). */
export type HudBlockView = {
  asOf: string;
  daily: HudDaily | null;
  theaters: HudTheater[];
  pulses: HudPulse[];
  coming: CalendarRow[];
  sanctions: SanctionsRow[];
  trader: HudTrader | null;
};
export type HudView = ViewEnvelope & { globe: GlobeData | null; hud: HudBlockView };

export type DailyHubView = ViewEnvelope & {
  desks: { desk: string; date: string; dates_total: number; recent: string[]; report: unknown | null }[];
};

export type GraphView = ViewEnvelope & {
  theaters: TheaterRefView[];
  ties: Record<string, Record<string, number>>;
  names: Record<string, string>;
  linkable: string[];
};

/** `fields` names the columns of each row, so the index can grow a column without breaking readers. */
export type SearchIndexView = ViewEnvelope & {
  fields: { entities: string[]; documents: string[] };
  entities: [string, string, string, number, string[]][];
  entities_total: number;
  documents: [string, string, string, string, string][];
};
