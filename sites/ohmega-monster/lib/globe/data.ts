// The payload the /globe page hands the viewer: compact, JSON-safe, client-safe types only (the server-side builder is lib/globe-data.ts).

import type { CountryRow, Dir } from "./channels";
import type { Theme } from "./themes";

/** A theater a country is tied to (for the side panel). `href` is its page, "" when it has no dossier. */
export type CountryTheater = { id: string; name: string; dir: Dir; href: string };

/** The newest daily mention of a country: a headline and where it lives. */
export type CountryHeadline = { text: string; date: string; href: string };

export type CountryInfo = CountryRow & {
  name: string;
  theaters: CountryTheater[];
  headline: CountryHeadline | null;
  /** True when /intel/actors/[iso] has something to show. */
  page: boolean;
};

/** A theater as a dot on the globe. `lon`/`lat` are null when the reports gave no coordinates (the viewer then falls back to the
 *  middle of its countries). `href` is the theater's latest daily section. */
export type GlobeTheater = { id: string; name: string; dir: Dir; heat: number; lon: number | null; lat: number | null; iso: string[]; href: string; date: string };

export type GlobeData = {
  /** Date of the newest daily the data is read against. */
  asOf: string;
  countries: Record<string, CountryInfo>;
  theaters: GlobeTheater[];
};

/** One stat row of the country panel. `pos` (0..1) places the value on a log track where the tick at 0.5 is the world median (a decade
 *  either side spans the track); null when there is no median to compare with. */
export type PanelStat = { id: string; label: string; text: string; year: number; pos: number | null; median: string };

/** One brief item that names a country (a daily report section or development), for the panel's history. `theme` is the same
 *  classification the map fill uses (lib/globe/themes.ts), so its dot matches the legend. */
export type CountryBrief = { theme: Theme; date: string; text: string; href: string; kind: "section" | "development" };

/** What /api/globe/country/[iso] returns: the supplemental stats and counts for one country (fetched when it is picked). */
export type CountryPanel = {
  iso: string;
  stats: PanelStat[];
  counts: { theaters: number; statements7d: number; sanctions30d: number; calendar: number; anomalies: number };
  grid: { line: string; asOf: string } | null;
  leaders: { head_of_state: string; head_of_government: string };
  /** Every brief item naming the country, newest first. */
  briefs: CountryBrief[];
};
