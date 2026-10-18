// Turns the published flows document into what the canvas draws: lane paths with their dots, trade arcs, place marks. Pure TS (no DOM),
// done once per document; the per-frame painter (paint.ts) only moves and projects what is built here.
//
// Dots are real in proportion. A lane that carries `rate` ships a day over `km` at `speed` km a day has rate x km / speed ships on it
// at any moment; that is how many dots it would show. All lanes are thinned by one common factor so the total stays under DOT_BUDGET
// (the scene says what that factor is, so the legend can say "1 dot ~ 3 ships"); a lane with any traffic keeps at least one dot.

import { buildPath, hash01, kmOf, toVec, type Path, type Vec } from "./geometry";
import { COMMODITY_IDS, SHIP_IDS, SHIP_KM_PER_DAY } from "./style";
import type { CommodityId, FlowsDoc, LayerId, ShipId, TradeBlock } from "./types";

/** Seconds of screen time one day of ship travel takes (a 13-knot tanker crosses a 1,000 km lane in about four seconds). */
export const SIM_DAY_S = 2.0;
export const DOT_BUDGET = 1400;
const TOP_LABELS = 5;

export type DotGroup = { cls: ShipId; n: number; /** radians of lane per second */ speed: number; seed: number };

export type ShipLane = {
  key: string;
  a: string;
  b: string;
  path: Path;
  /** Ships a day by class (7-day), and the sum. */
  by: Partial<Record<ShipId, number>>;
  rate: number;
  groups: DotGroup[];
  /** The lane breathes at this rate (cycles a second): busier lanes faster. */
  pulseHz: number;
  phase: number;
  mid: Vec;
  /** Plain label: "Hormuz to Gulf of Oman" and the rate. */
  label: string;
};

export type Arc = {
  key: string;
  layer: CommodityId | "money";
  path: Path;
  /** Stroke width in pixels at zoom 1. */
  width: number;
  /** 0..1 by value within its layer: the largest flows are drawn strongest. */
  weight: number;
  value: number;
  /** Rank by value within its layer (0 = largest). */
  rank: number;
  label: string;
  /** The label is for this layer's largest few. */
  labelled: boolean;
};

export type PlaceMark = {
  id: string;
  label: string;
  kind: "chokepoint" | "region";
  v: Vec;
  r7: number;
  dir: "above" | "below" | null;
  note: string;
};

export type Scene = {
  lanes: ShipLane[];
  arcs: Arc[];
  places: PlaceMark[];
  /** Ships per dot (>= 1). */
  thin: number;
  rmax: number;
  /** Ships a day entering the watched chokepoints, by class (the legend's number). */
  passages: Partial<Record<ShipId, number>>;
};

export const fmtRate = (r: number): string => (r >= 10 ? String(Math.round(r)) : r >= 1 ? r.toFixed(1) : r.toFixed(2));

export function fmtUsd(u: number): string {
  if (u >= 1e12) return `$${(u / 1e12).toFixed(1)}T`;
  if (u >= 1e9) return `$${(u / 1e9).toFixed(u >= 1e10 ? 0 : 1)}B`;
  return `$${Math.round(u / 1e6)}M`;
}

export function fmtTonnes(t: number): string {
  return t >= 1e6 ? `${(t / 1e6).toFixed(t >= 1e7 ? 0 : 1)} Mt` : `${Math.round(t / 1e3)} kt`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2026-10-17" -> "17 Oct". */
const shortDay = (iso: string): string => `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1] ?? ""}`.trim();

const titleCase =(id: string): string => id.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function shipRates(by: Partial<Record<ShipId, number>>): number {
  return SHIP_IDS.reduce((s, c) => s + (by[c] ?? 0), 0);
}

/** Only a layer's largest flows are drawn (a screen of arcs is a reader budget, not a statement that the rest do not exist). */
const ARC_CAP: Record<CommodityId | "money", number> = { wheat: 18, maize: 14, soy: 12, money: 26 };

function buildArcs(layer: CommodityId | "money", block: TradeBlock, doc: FlowsDoc): Arc[] {
  const ranked = block.flows.filter((f) => doc.places[f.from] && doc.places[f.to]).sort((a, b) => b.usd - a.usd).slice(0, ARC_CAP[layer]);
  if (ranked.length === 0) return [];
  const lo = Math.log(Math.max(1, ranked[ranked.length - 1].usd)), hi = Math.log(Math.max(2, ranked[0].usd));
  return ranked.map((f, rank) => {
    const a = doc.places[f.from], b = doc.places[f.to];
    const t = hi > lo ? (Math.log(Math.max(1, f.usd)) - lo) / (hi - lo) : 0.5;
    const what = layer === "money" ? fmtUsd(f.usd) : `${fmtTonnes(f.t)} (${fmtUsd(f.usd)})`;
    return {
      key: `${layer}:${f.from}>${f.to}`,
      layer,
      path: buildPath([[a.lat, a.lon], [b.lat, b.lon]], 2, 0.07),
      width: 0.9 + 2.7 * t,
      weight: 0.35 + 0.65 * t,
      value: f.usd,
      rank,
      label: `${layer === "money" ? "" : `${block.label}: `}${a.name} to ${b.name}, ${what}, ${f.period}`,
      labelled: rank < TOP_LABELS,
    };
  });
}

export function buildScene(doc: FlowsDoc): Scene {
  const name = new Map(doc.ais.places.map((p) => [p.id, p.label]));
  const nameOf = (id: string) => name.get(id) ?? titleCase(id);
  // lanes: the rates by class as published (the 7-day ones; the 30-day ones stand in for a lane quiet this week)
  const raw = doc.ais.lanes.map((l) => ({ l, by: l.by, path: buildPath(l.line, 1.5, 0) })).filter((x) => shipRates(x.by) > 0 && x.path.n > 1);
  const real = (x: (typeof raw)[number], c: ShipId): number => ((x.by[c] ?? 0) * kmOf(x.path.total)) / SHIP_KM_PER_DAY[c];
  const totalReal = raw.reduce((s, x) => s + SHIP_IDS.reduce((u, c) => u + real(x, c), 0), 0);
  const thin = Math.max(1, totalReal / DOT_BUDGET);
  const rmax = Math.max(1e-6, ...raw.map((x) => shipRates(x.by)));
  const lanes: ShipLane[] = raw.map((x, li) => {
    const rate = shipRates(x.by);
    const mid: Vec = [0, 0, 0];
    const ix = Math.floor(x.path.n / 2) * 3;
    mid[0] = x.path.v[ix]; mid[1] = x.path.v[ix + 1]; mid[2] = x.path.v[ix + 2];
    return {
      key: `${x.l.a}>${x.l.b}`,
      a: x.l.a,
      b: x.l.b,
      path: x.path,
      by: x.by,
      rate,
      groups: SHIP_IDS.filter((c) => (x.by[c] ?? 0) > 0).map((c, ci) => ({
        cls: c,
        n: Math.max(1, Math.round(real(x, c) / thin)),
        speed: SHIP_KM_PER_DAY[c] / 6371 / SIM_DAY_S,
        seed: li * 16 + ci,
      })),
      pulseHz: 0.12 + 1.2 * (rate / rmax),
      phase: hash01(li * 7 + 3) * Math.PI * 2,
      mid,
      label: `${nameOf(x.l.a)} to ${nameOf(x.l.b)}, ${fmtRate(rate)} a day`,
    };
  });
  // places: chokepoints always; any place whose latest day sits outside its own normal
  const places: PlaceMark[] = doc.ais.places
    .filter((p) => p.kind === "chokepoint" || p.dir)
    .map((p) => ({
      id: p.id,
      label: p.label,
      kind: p.kind,
      v: toVec(p.lat, p.lon),
      r7: p.r7,
      dir: p.dir ?? null,
      note: p.dir && p.usual !== undefined && p.last !== undefined
        ? `${p.label}: ${fmtRate(p.last)} ships ${p.day ? `on ${shortDay(p.day)}` : "in the last day"}, usually ${fmtRate(p.usual)}`
        : `${p.label}: ${fmtRate(p.r7)} a day`,
    }));
  const passages: Partial<Record<ShipId, number>> = {};
  for (const p of doc.ais.places) if (p.kind === "chokepoint") for (const c of SHIP_IDS) passages[c] = (passages[c] ?? 0) + (p.by[c] ?? 0);
  // trade arcs
  const arcs: Arc[] = [];
  for (const c of COMMODITY_IDS) {
    const block = doc.grain?.commodities[c];
    if (block) arcs.push(...buildArcs(c, block, doc));
  }
  if (doc.money) arcs.push(...buildArcs("money", doc.money, doc));
  return { lanes, arcs, places, thin, rmax, passages };
}

/** Layers this document can show at all (a layer with nothing in it is not offered). */
export function availableLayers(doc: FlowsDoc): LayerId[] {
  const out: LayerId[] = SHIP_IDS.filter((c) => doc.ais.lanes.some((l) => (l.by[c] ?? 0) > 0));
  for (const c of COMMODITY_IDS) if (doc.grain?.commodities[c]?.flows.length) out.push(c);
  if (doc.money?.flows.length) out.push("money");
  return out;
}
