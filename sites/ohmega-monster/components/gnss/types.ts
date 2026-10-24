// The `gnss` document the server publishes next to `flows` (backend gnss/publish.py `snapshot_doc`, live/gnss.json): the newest day's interference zones,
// compact, plus the provenance of each source for the legend.

export type GnssZoneDot = {
  lat: number;
  lon: number;
  /** Cell edge in degrees. */
  r: number;
  s: "low" | "medium" | "high";
  /** Share of aircraft observations degraded, 0 to 1. */
  share: number;
  /** "", "new" or "intensifying". */
  f: string;
  /** "o": Ohmega's own estimate; "g": GPSJam. */
  src: "o" | "g";
};

export type GnssSourceNote = { basis: string; coverage_note: string; baseline_since?: string; baseline_days?: number };

export type GnssDoc = {
  v: 1;
  as_of: string;
  date: string;
  zones: GnssZoneDot[];
  p: { ours: GnssSourceNote; gpsjam: GnssSourceNote };
};
