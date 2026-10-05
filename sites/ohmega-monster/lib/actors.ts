import fs from "node:fs";
import path from "node:path";

import { safeUrl, type Band } from "./intel";

// Actors: one power profile per state, written by the backend (publishing/actors_feed.py) as
// <intel dir>/actors/<ISO2>.json (ohmega.actor/1) plus index.json, read at build time. Parsed
// defensively: a missing dir or malformed file yields empty states, never a build failure.
const INTEL_DIR = process.env.OHMEGA_INTEL_DIR || path.join(process.cwd(), "content", "intel");
const ACTORS_DIR = path.join(INTEL_DIR, "actors");
const ISO_RE = /^[A-Z]{2}$/;

export type Unit = "people" | "usd" | "pct" | "twh" | "kwh" | "km2" | "persons" | "months" | "number";
export type Field = { id: string; label: string; unit: Unit; value: number; year: number; source: string; rank?: number; of?: number; percentile?: number };
export type Official = { name: string; since: string };
export type Nuclear = { status: string; stockpile: number; inventory: number; year: number; source_url: string };
export type ActorStatement = { id: string; speaker: string; role: string; date: string; text: string; is_quote: boolean; signal: string; stance: number; source_url: string };
export type Involved = {
  theaters: { id: string; name: string; mentions: number }[];
  pulses: { id: string; name: string; band: Band; position: number | null; theater_id: string }[];
};
export type Credit = { source: string; name: string; licence: string; url: string; years: string };
export const GROUPS = ["people", "economy", "trade", "energy", "military"] as const;
export type GroupId = (typeof GROUPS)[number];
export type Actor = {
  iso2: string;
  name: string;
  region: string;
  capital: string;
  data_as_of: string;
  headline: Field[];
  groups: Record<GroupId, Field[]>;
  energy_role: { surplus: string[]; deficit: string[] };
  leadership: { head_of_state: Official | null; head_of_government: Official | null; as_of: string; nuclear: Nuclear | null };
  statements: ActorStatement[];
  involved: Involved;
  credits: Credit[];
};

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string => (typeof v === "string" ? v : typeof v === "number" ? String(v) : "");
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const objs = (v: unknown): Obj[] => arr(v).filter(isObj);

function readJson(file: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

function field(r: Obj): Field | null {
  const value = num(r.value);
  const year = num(r.year);
  if (value === null || year === null || !str(r.id)) return null;
  const f: Field = { id: str(r.id), label: str(r.label), unit: (str(r.unit) || "number") as Unit, value, year, source: str(r.source) };
  const rank = num(r.rank);
  const of = num(r.of);
  if (rank !== null && of !== null) {
    f.rank = rank;
    f.of = of;
    f.percentile = num(r.percentile) ?? undefined;
  }
  return f;
}
const fields = (v: unknown): Field[] => objs(v).map(field).filter((f): f is Field => f !== null);
const official = (v: unknown): Official | null => (isObj(v) && str(v.name) ? { name: str(v.name), since: str(v.since) } : null);
const BANDS = ["calm", "elevated", "severe", "critical", "unassessed"];

function parseActor(raw: unknown): Actor | null {
  if (!isObj(raw)) return null;
  const iso2 = str(raw.iso2);
  if (!ISO_RE.test(iso2)) return null;
  const groupsRaw = isObj(raw.groups) ? raw.groups : {};
  const lead = isObj(raw.leadership) ? raw.leadership : {};
  const nuc = isObj(lead.nuclear) ? lead.nuclear : null;
  const inv = isObj(raw.involved) ? raw.involved : {};
  const role = isObj(raw.energy_role) ? raw.energy_role : {};
  return {
    iso2,
    name: str(raw.name) || iso2,
    region: str(raw.region),
    capital: str(raw.capital),
    data_as_of: str(raw.data_as_of),
    headline: fields(raw.headline),
    groups: Object.fromEntries(GROUPS.map((g) => [g, fields(groupsRaw[g])])) as Record<GroupId, Field[]>,
    energy_role: { surplus: arr(role.surplus).map(str).filter(Boolean), deficit: arr(role.deficit).map(str).filter(Boolean) },
    leadership: {
      head_of_state: official(lead.head_of_state),
      head_of_government: official(lead.head_of_government),
      as_of: str(lead.as_of),
      nuclear: nuc ? { status: str(nuc.status), stockpile: num(nuc.stockpile) ?? 0, inventory: num(nuc.inventory) ?? 0, year: num(nuc.year) ?? 0, source_url: safeUrl(str(nuc.source_url)) ?? "" } : null,
    },
    statements: objs(raw.statements).map((s) => ({
      id: str(s.id), speaker: str(s.speaker), role: str(s.role), date: str(s.date), text: str(s.text),
      is_quote: s.is_quote === true, signal: str(s.signal), stance: num(s.stance) ?? 0, source_url: safeUrl(str(s.source_url)) ?? "",
    })).filter((s) => s.text),
    involved: {
      theaters: objs(inv.theaters).map((t) => ({ id: str(t.id), name: str(t.name), mentions: num(t.mentions) ?? 0 })).filter((t) => t.id),
      pulses: objs(inv.pulses).map((p) => ({
        id: str(p.id), name: str(p.name), band: (BANDS.includes(str(p.band)) ? str(p.band) : "unassessed") as Band,
        position: num(p.position), theater_id: str(p.theater_id),
      })).filter((p) => p.id),
    },
    credits: objs(raw.credits).map((c) => ({ source: str(c.source), name: str(c.name), licence: str(c.licence), url: safeUrl(str(c.url)) ?? "", years: str(c.years) })),
  };
}

export function actorIds(): string[] {
  try {
    return fs.readdirSync(ACTORS_DIR).filter((f) => /^[A-Z]{2}\.json$/.test(f)).map((f) => f.slice(0, 2)).sort();
  } catch {
    return [];
  }
}

export function actor(iso2: string): Actor | null {
  return ISO_RE.test(iso2) ? parseActor(readJson(path.join(ACTORS_DIR, `${iso2}.json`))) : null;
}

export function allActors(): Actor[] {
  return actorIds().map(actor).filter((a): a is Actor => a !== null);
}

/** The published actors a theater involves, most mentioned first. */
export function actorsForTheater(theaterId: string): Actor[] {
  return allActors()
    .map((a) => ({ a, n: a.involved.theaters.find((t) => t.id === theaterId)?.mentions ?? 0 }))
    .filter((x) => x.n > 0)
    .sort((x, y) => y.n - x.n || x.a.name.localeCompare(y.a.name))
    .map((x) => x.a);
}

export const headlineOf = (a: Actor, id: string): Field | null => a.headline.find((f) => f.id === id) ?? null;
export const fieldOf = (a: Actor, id: string): Field | null => GROUPS.flatMap((g) => a.groups[g]).find((f) => f.id === id) ?? null;

// ---- display ------------------------------------------------------------------------------
const STEPS: [number, string][] = [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "k"]];
export function compact(v: number): string {
  for (const [size, suffix] of STEPS) {
    if (Math.abs(v) >= size) {
      const n = v / size;
      return (Math.abs(n) >= 100 ? n.toFixed(0) : n.toFixed(1).replace(/\.0$/, "")) + suffix;
    }
  }
  return Math.abs(v) >= 10 ? Math.round(v).toLocaleString("en-US") : v.toFixed(1);
}
export function fmt(v: number, unit: Unit): string {
  switch (unit) {
    case "usd": return "$" + compact(v);
    case "pct": return v.toFixed(1) + "%";
    case "twh": return compact(v) + " TWh";
    case "kwh": return (v / 1000).toFixed(1) + " MWh";
    case "km2": return compact(v) + " km²";
    case "months": return v.toFixed(1) + " mo";
    default: return compact(v);
  }
}
export const CREDIT_SOURCE_ORDER = ["wb", "owid", "imf", "wikidata", "nuclear"];
