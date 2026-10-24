// The rules of honest numbers, as one pure function (no I/O, client-safe). `statView` takes a registry id and a value and returns how the number
// must be worded and whether its comparison may be shown; `<Stat>` (components/stats/Stat.tsx) and the data builders (lib/glance.ts, lib/globe-hud.ts)
// both use it, so a rule lives in exactly one place:
//   our_count   -> a minimum ("≥ 52"; "0 heard" for zero), never a bare number
//   model       -> marked model-assessed
//   a cap       -> "latest 1,500" unless the real total is known
//   a comparison against OUR history -> withheld until `min_history`, replaced by "collecting since 11 Oct"
// docs/architecture/information-architecture.md section 4.

import { BASIS_LABEL, statDef, type StatDef } from "./registry";

/** One layer of the live summary's `provenance` block (backend live/provenance.py). Every field is optional: older documents have none. */
export type LayerProv = { basis?: string; since?: string; history_days?: number; scope?: string; coverage_note?: string };
export type Provenance = Partial<Record<"ships" | "aircraft" | "fires", LayerProv>> & { min_history_days?: number };

export type Compare =
  /** Against our own recent normal. Withheld until our history meets the stat's floor. */
  | { kind: "usual"; pct: number | null }
  /** Against the source's own earlier figure (a year ago, the prior week). Official, so always allowed. */
  | { kind: "prior"; pct: number | null; label: string }
  /** A two-point comparison with one earlier value ("vs 27 on 12 Oct"); never "vs usual". */
  | { kind: "two_point"; label: string };

export type StatInput = {
  id: string;
  value: number | string | null;
  digits?: number;
  compare?: Compare;
  /** Length of OUR series behind the value, when the caller knows it. */
  history?: { days: number; since?: string };
  /** The live summary's provenance block; supplies `since`, `history_days` and the floor from data. */
  provenance?: Provenance;
  /** Which layer of `provenance` this stat belongs to (defaults to the registry's `since_from` when that names a layer). */
  layer?: "ships" | "aircraft" | "fires";
  /** A list/export that was cut at `limit`; with `total` the real size is shown instead of the cap. */
  cap?: { limit: number; total?: number | null };
  /** The window the number covers, named ("last 30 days"). */
  window?: string;
  /** Extra hover line for this particular render (what a sum covers, a share of one part). */
  note?: string;
};

export type StatView = {
  def: StatDef;
  /** The number as it must be read: "≥ 52", "latest 1,000", "0 heard", "74.6". */
  text: string;
  minimum: boolean;
  model: boolean;
  capped: boolean;
  window: string;
  /** Present only when a comparison is allowed. */
  comparison: { text: string; sign: number } | null;
  /** Present instead of a comparison while our history is shorter than the floor: "collecting since 11 Oct". */
  collecting: string | null;
  /** The info hover, 2 to 4 plain lines. */
  lines: string[];
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const fmtNum = (n: number, digits = 0): string => n.toLocaleString("en-US", { maximumFractionDigits: digits });
export const signed = (n: number, digits = 0): string => `${n > 0 ? "+" : n < 0 ? "−" : ""}${fmtNum(Math.abs(n), digits)}`;

/** "2026-10-11" -> "11 Oct" (UTC); the input back when it is not a plain date. */
export function shortDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1] ?? ""}` : iso;
}

/** Whole days from a YYYY-MM-DD to `nowMs`; null when it is not a date. */
export function daysSince(iso: string, nowMs: number = Date.now()): number | null {
  const t = Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isFinite(t) ? Math.max(0, Math.floor((nowMs - t) / 86400000)) : null;
}

/** Days of our own series, from the provenance block or from the earliest and latest period the caller holds. */
export function historyOf(periods: string[]): { days: number; since: string } | undefined {
  const ok = periods.filter((p) => /^\d{4}-\d{2}-\d{2}/.test(p)).sort();
  if (ok.length === 0) return undefined;
  const t0 = Date.parse(`${ok[0]}T00:00:00Z`);
  const t1 = Date.parse(`${ok[ok.length - 1]}T00:00:00Z`);
  return { days: Math.round((t1 - t0) / 86400000) + 1, since: ok[0] };
}

function resolve(def: StatDef, i: StatInput) {
  const layer = i.layer ?? (def.since_from === "ships" || def.since_from === "aircraft" || def.since_from === "fires" ? def.since_from : undefined);
  const prov = layer ? i.provenance?.[layer] : undefined;
  const since = i.history?.since || prov?.since || def.baseline_since || "";
  const days = i.history?.days ?? prov?.history_days ?? (since ? daysSince(since) : null);
  const floor = i.provenance?.min_history_days ?? def.min_history;
  return { since, days, floor, prov };
}

/** A count that can only be a floor: our own partial-sensor counts, machine-coded counts, and any entry that says so. */
export const isMinimum = (def: StatDef): boolean => def.minimum ?? (def.basis === "our_count" || def.basis === "machine_coded");

function valueText(def: StatDef, i: StatInput, capped: boolean): string {
  if (i.value === null || i.value === undefined || i.value === "") return "–";
  const n = typeof i.value === "number" ? fmtNum(i.value, i.digits ?? 0) : i.value;
  if (capped) return `latest ${n}`;
  if (isMinimum(def) && typeof i.value === "number") return i.value === 0 ? (def.basis === "our_count" ? "0 heard" : "none seen") : `≥ ${n}`;
  return n;
}

function infoLines(def: StatDef, since: string, days: number | null, floor: number | null, prov: LayerProv | undefined, note?: string): string[] {
  const out = [`${BASIS_LABEL[def.basis]}: ${def.source.name}.`, `Counts: ${prov?.scope || def.scope}`];
  const limit = prov?.coverage_note || def.coverage;
  if (limit) out.push(`${isMinimum(def) ? "Why a minimum" : "Limit"}: ${limit}`);
  if (note) out.push(note);
  const unit = def.history_unit;
  const mine = since ? `our own series since ${shortDate(since)}${days !== null ? ` (${days} ${days === 1 ? "day" : "days"} so far)` : ""}` : "our own series";
  out.push(
    def.baseline === "our_history"
      ? `Baseline: ${mine}${floor ? `; no comparison is shown before ${floor} ${unit} (${def.min_history_origin}).` : "."}`
      : def.baseline === "official_prior"
        ? "Baseline: the source's own earlier figures, not ours."
        : "Baseline: none; a single reading.",
  );
  return out.slice(0, 5);
}

export function statView(i: StatInput): StatView {
  const def = statDef(i.id);
  const { since, days, floor, prov } = resolve(def, i);
  const nValue = typeof i.value === "number" ? i.value : null;
  const capped = !!i.cap && i.cap.total == null && nValue !== null && nValue >= i.cap.limit;
  const shown = i.cap && i.cap.total != null ? { ...i, value: i.cap.total } : i;

  let comparison: StatView["comparison"] = null;
  let collecting: string | null = null;
  const c = i.compare;
  if (c?.kind === "usual" && c.pct !== null) {
    const mature = def.baseline !== "our_history" || (floor !== null && days !== null && days >= floor);
    if (mature) comparison = { text: `${signed(c.pct)}% vs usual`, sign: c.pct };
    else collecting = since ? `collecting since ${shortDate(since)}` : "collecting history";
  } else if (c?.kind === "prior" && c.pct !== null) {
    comparison = { text: `${signed(c.pct, Math.abs(c.pct) < 10 ? 1 : 0)}% ${c.label}`, sign: c.pct };
  } else if (c?.kind === "two_point") {
    comparison = { text: c.label, sign: 0 };
  }
  return {
    def,
    text: valueText(def, shown, capped),
    minimum: isMinimum(def),
    model: def.basis === "model",
    capped,
    window: i.window ?? "",
    comparison,
    collecting,
    lines: infoLines(def, since, days, floor, prov, i.note),
  };
}

/** A hit rate (share of closed positions that ended in profit). A ratio on a handful of positions says nothing, so it is withheld until `n` reaches
 *  `min` (the backend's MIN_RESOLVED_FOR_VERDICT, published as `rules.min_for_verdict`); until then the counts are the honest figure. */
export function hitRateView(rate: number | null, n: number, min: number): { text: string; note: string } {
  if (rate === null || n < min) return { text: "–", note: `rate shown once ${min} have closed` };
  return { text: `${Math.round(rate * 100)}%`, note: "" };
}
