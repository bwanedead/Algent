// The payload the /globe HUD panels read: compact, JSON-safe, client-safe types only (the server-side builder is lib/globe-hud.ts).
// Every field is real published data; a source that is missing yields null or an empty list, never an invented value.

import type { Band, Direction, Pace, Trend } from "../intel";
import type { Theme } from "./themes";

/** One line of today's report: a theater's headline or a development, with the theme the map fill uses (lib/globe/themes.ts). */
export type HudItem = { theme: Theme; text: string; href: string; date: string; kind: "section" | "development"; iso: string[] };

export type HudDaily = { date: string; headline: string; items: HudItem[] };

/** A tracked question ("Pulse") with the history its sparkline draws. */
export type HudPulse = {
  id: string;
  title: string;
  band: Band;
  position: number | null;
  change7d: number | null;
  /** Position readings, oldest first (at most 30). */
  history: number[];
  iso: string[];
  href: string;
};

export type HudTheater = {
  id: string;
  name: string;
  heat: number;
  trend: Trend;
  dir: Direction;
  pace: Pace;
  /** The writer's one-sentence headline (else a cut of the bottom line). */
  line: string;
  href: string;
  iso: string[];
  pulses: HudPulse[];
};

/** One live counter: the latest completed day of one of our own feeds against its recent normal. */
export type HudCounter = {
  key: "aircraft" | "ships" | "fires" | "quakes" | "outages";
  label: string;
  value: number;
  /** The value as the stats registry words it ("≥ 55", "0 heard"). */
  text: string;
  unit: string;
  /** Against the median of the days before; null while our own history is too young (then `collecting` says since when) or too short to call a normal. */
  delta: { text: string; sign: number } | null;
  collecting: string | null;
  spark: number[];
  href: string;
  /** Registry id and the plain hover lines (basis, source, scope, why a minimum, baseline). */
  statId: string;
  info: string[];
};
export type HudAnomaly = { id: string; sentence: string; direction: "above" | "below"; confidence: number; ongoing: boolean; iso: string[] };
export type HudLive = { counters: HudCounter[]; anomalies: HudAnomaly[] };

export type HudComing = { date: string; end: string; title: string; kind: string; label: string; iso: string[]; url: string; ours: boolean; until: string };
export type HudSanction = { id: string; name: string; type: string; source: string; date: string; iso: string[]; programme: string; url: string };

/** One reported attack for the HUD (see lib/conflict-shared.ts). `machine` marks software-read news (GDELT). */
export type HudAttack = { id: string; date: string; type: string; place: string; iso: string[]; source: string; machine: boolean; fatalities: number | null; reports: number; url: string };
/** The attack panel: the strongest recent rows and the count of everything stored in the window (a minimum: registry id `attacks_events`). */
export type HudAttacks = { rows: HudAttack[]; total: number; days: number };
export type HudJam = { id: string; where: string; iso: string[]; severity: "low" | "medium" | "high"; share: number; flag: "" | "new" | "intensifying"; lat: number; lon: number };
/** The GPS-interference panel: the strongest zones of the newest day from Ohmega's own estimate (registry id `gnss_zones`). */
export type HudGnss = { day: string; zones: HudJam[]; total: number };

export type HudTrader = {
  asOf: string;
  bankroll: number;
  equity: number;
  pnl: number;
  open: number;
  /** Daily equity of the trader against the flat bankroll (doing nothing). */
  curve: { day: string; flat: number; trader: number }[];
  positions: { question: string; side: "yes" | "no"; pnl: number; value: number; url: string }[];
};

/** DATA CONTRACT for the "Tweets of the day" panel. Nothing publishes this yet (the X intake stays in the backend, and no table or
 *  document carries its items), so `HudData.tweets` is null and the panel says so. To light it up, publish a document or table of
 *  this shape for the day (curated, pre-vetted posts only) and have lib/globe-hud.ts read it into `HudData.tweets`. */
export type HudTweet = {
  id: string;
  /** Display name and @handle of the author. */
  author: string;
  handle: string;
  text: string;
  /** Canonical post URL on x.com. */
  url: string;
  /** ISO 8601 time the post was made. */
  at: string;
  /** Why it is notable, one short line (ours, not the author's). */
  why: string;
  /** ISO alpha-2 codes of the places it concerns (lets hovering highlight the globe). */
  iso: string[];
};

export type HudData = {
  asOf: string;
  daily: HudDaily | null;
  theaters: HudTheater[];
  pulses: HudPulse[];
  live: HudLive | null;
  coming: HudComing[];
  sanctions: HudSanction[];
  attacks: HudAttacks | null;
  gnss: HudGnss | null;
  trader: HudTrader | null;
  tweets: HudTweet[] | null;
};
