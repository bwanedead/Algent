// The payload the /globe page hands the viewer: compact, JSON-safe, client-safe types only (the server-side builder is lib/globe-data.ts).

import type { CountryRow, Dir } from "./channels";

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
