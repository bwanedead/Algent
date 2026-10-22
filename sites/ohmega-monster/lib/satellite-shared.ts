// Client-safe types and pure helpers of the satellite watch (backend `satellite/`, document `live/satellite.json` in the public bucket).
// Server reads live in lib/satellite.ts. Every number the backend publishes carries its provenance (`basis`, `method_note`, `baseline_since`,
// `n_obs`); `provText` turns it into the sentence the info hover shows, so a site with little history says so instead of implying a long baseline.

import { DATA_BASE, dataUrl } from "./data-base";

export type Provenance = {
  /** "our_computation": computed by Ohmega from the imagery, not reported by a source. */
  basis: string;
  method_note: string;
  /** When our own history for this site starts (YYYY-MM-DD), or null when it starts with this look. */
  baseline_since: string | null;
  /** Earlier looks the judgement rests on. */
  n_obs: number;
};

export type SceneMeta = {
  scene: string;
  date: string;
  tile_cloud_pct: number;
  local_cloud_pct: number;
  nodata_pct: number;
  /** Bucket key of the chip: satellite/<site>/<date>-<hash>.png */
  chip: string;
  source: string;
  before_event?: boolean;
};

export type ChangeLabel = "changed" | "steady" | "learning" | "inconclusive";
export type NightLabel = "dimmer" | "brighter" | "steady" | "learning";

export type Change = Provenance & {
  label: ChangeLabel;
  score: number | null;
  changed_frac: number | null;
  valid_share: number;
  z: number | null;
  usual: number | null;
  reason: string;
};

export type Night = Partial<Provenance> & {
  date: string;
  value: number;
  lit_share: number;
  label: NightLabel;
  z: number | null;
  usual: number | null;
  reason: string;
  source: string;
};

export type SatSite = {
  id: string;
  name: string;
  kind: "asset" | "zone";
  asset_type: string;
  lat: number;
  lon: number;
  half_km: number;
  bbox: [number, number, number, number];
  priority: number;
  why: string[];
  event_on: string | null;
  countries: string[];
  links: { asset?: string; country?: string; theater?: string };
  state: string;
  note: string;
  checked_at: string | null;
  baseline: SceneMeta | null;
  latest: SceneMeta | null;
  change: Change | null;
  night: Night | null;
};

export type SatelliteDoc = {
  v: 1;
  as_of: string;
  credit: string;
  read_as: string;
  pass: Record<string, unknown>;
  counts: { watched: number; with_imagery: number; changed: number; dimmer: number };
  sites: SatSite[];
};



/** Where a chip is served from (the public object store); "" when the site has no bucket configured. */
export const chipUrl = (key: string): string => (DATA_BASE ? dataUrl(key) : "");

export const CHANGE_WORD: Record<ChangeLabel, string> = {
  changed: "Changed",
  steady: "Steady",
  learning: "Learning",
  inconclusive: "Inconclusive",
};
export const NIGHT_WORD: Record<NightLabel, string> = { dimmer: "Dimmer", brighter: "Brighter", steady: "Steady", learning: "Learning" };

/** The sentence behind an info hover: how a number was made, by whom, and how much of our own history it rests on. */
export function provText(p: Partial<Provenance>): string {
  const n = p.n_obs ?? 0;
  const since = p.baseline_since ? `Our history for this site starts ${p.baseline_since}` : "Our history for this site starts with this look";
  const thin = n < 5 ? " That is too few looks to say what is normal for it." : "";
  return `${p.method_note ?? ""} Computed by Ohmega (${p.basis ?? "our_computation"}). ${since}; ${n} earlier ${n === 1 ? "look" : "looks"}.${thin}`.trim();
}

/** Display order: flagged change first, then a night-light fall, then the biggest score, then the desk's own priority. */
export function bySignal(a: SatSite, b: SatSite): number {
  const rank = (s: SatSite): number => (s.change?.label === "changed" ? 0 : s.night?.label === "dimmer" ? 1 : 2);
  return rank(a) - rank(b) || (b.change?.score ?? -1) - (a.change?.score ?? -1) || b.priority - a.priority;
}

export const pct = (v: number | null | undefined, digits = 1): string => (v === null || v === undefined ? "n/a" : `${(v * 100).toFixed(digits)}%`);
