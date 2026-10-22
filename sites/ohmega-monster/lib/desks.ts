// The desks: the topics that own Dailies and Situations (docs/architecture/information-architecture.md §1). This is the site's
// mirror of the backend registry (agents/intel/domains.py REGISTRY); a new desk is ONE entry here, and every hub (the Daily
// hub, the Situations tabs, Home) lists it from this array, so nothing else needs touching. Pure data, safe in client code.

export type Desk = {
  /** The backend domain id; also the folder of its dailies (`daily/<id>/<date>.json`) and its URL segment. */
  id: string;
  label: string;
  /** One line saying what the desk covers. */
  blurb: string;
  /** When the desk's parts of the day go out (UTC "HH:MM"), mirroring the backend timers; one entry = one part a day. */
  parts: string[];
  /** The Daily's cadence in hours; staleness is judged against it (lib/fresh.ts). */
  cadenceHours: number;
  /** Theater `domain` strings that belong to this desk. Legacy labels (`technology`) fold into the AI desk; geopolitics keeps the rest. */
  domains: string[];
  /** Other desks' domain strings are never counted here: geopolitics owns every domain no other desk claims. */
  catchAll?: boolean;
};

export const DESKS: Desk[] = [
  {
    id: "geopolitics",
    label: "Geopolitics",
    blurb: "The world's hot spots: what happened, who said what, what to watch next.",
    parts: ["05:30", "17:30"],
    cadenceHours: 24,
    domains: ["geopolitics"],
    catchAll: true,
  },
  {
    id: "ai",
    label: "AI",
    blurb: "The labs' race, chips and compute, policy, security, open weights and capital.",
    parts: ["09:00"],
    cadenceHours: 24,
    domains: ["ai", "technology"],
  },
];

/** "twice a day (05:30, 17:30 UTC)" / "once a day (09:00 UTC)". */
export const cadenceLine = (d: Desk): string =>
  `${d.parts.length === 1 ? "once a day" : d.parts.length === 2 ? "twice a day" : `${d.parts.length} times a day`} (${d.parts.join(", ")} UTC)`;

export const deskById = (id: string): Desk | undefined => DESKS.find((d) => d.id === id);

/** The desk a theater's free-word `domain` belongs to: a desk that names it, else the catch-all (geopolitics, which keeps legacy labels and blanks). */
export function deskOfDomain(domain: string): Desk {
  const d = (domain || "").trim().toLowerCase();
  return DESKS.find((x) => x.domains.includes(d)) ?? DESKS.find((x) => x.catchAll) ?? DESKS[0];
}

// ---- routes (one place, so a path never has to be rebuilt by hand) ------------------------------------------------------------------

/** The desk's newest Daily lives here; older ones at `${dailyBase(id)}/<date>`. */
export const dailyBase = (desk: string): string => `/daily/${desk}`;
export const dailyHref = (desk: string, date: string): string => `${dailyBase(desk)}/${date}`;
export const SITUATIONS = "/situations";
export const situationHref = (id: string): string => `${SITUATIONS}/${id}`;
