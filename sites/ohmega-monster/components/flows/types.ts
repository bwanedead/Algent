// The published `flows` document (backend `flows/document.py`, live Storage object `live/flows.json`). Client-safe types only.

export type ShipId = "tanker" | "lng" | "bulk" | "container" | "cargo";
export type CommodityId = "wheat" | "maize" | "soy";
/** One drawable layer: a ship class (observed, live), a grain, or money (public statistics, annual). */
export type LayerId = ShipId | CommodityId | "money";

export type FlowClassDef = { id: ShipId; label: string };

export type FlowLane = {
  a: string;
  b: string;
  /** The drawn path [lat, lon] from a to b (centre, waypoints, centre). */
  line: [number, number][];
  /** Ships a day over the last 7 and 30 days, all classes. */
  r7: number;
  r30: number;
  /** Ships a day by class over the last 7 days. */
  by: Partial<Record<ShipId, number>>;
  /** Hops counted in the longer window. */
  n: number;
  /** Share of those that were inferred across several lanes rather than seen on this one. */
  inf: number;
  /** Median hours of the observed direct hops (when any). */
  h?: number;
};

export type FlowPlace = {
  id: string;
  label: string;
  kind: "chokepoint" | "region";
  lat: number;
  lon: number;
  r7: number;
  r30: number;
  by: Partial<Record<ShipId, number>>;
  usual?: number;
  last?: number;
  z?: number;
  dir?: "above" | "below" | null;
  day?: string;
};

export type FlowsAis = {
  since: string | null;
  /** Days the tracker watched for most of the day. */
  days: number;
  windows: number[];
  note: string;
  /** Too few days to judge a place against its own normal. */
  learning: boolean;
  places: FlowPlace[];
  lanes: FlowLane[];
};

export type TradeFlow = { from: string; to: string; usd: number; t: number; period: string };
export type TradeBlock = { label: string; flows: TradeFlow[]; missing: string[] };
export type TradeMeta = { fetched_at: string | null; source: string | null; source_url: string | null; note: string };

export type FlowsDoc = {
  v: number;
  as_of: string;
  today: string;
  classes: FlowClassDef[];
  ais: FlowsAis;
  grain?: TradeMeta & { commodities: Partial<Record<CommodityId, TradeBlock>> };
  money?: TradeMeta & TradeBlock;
  /** Countries named by any trade flow, with the point their arcs start and end at. */
  places: Record<string, { name: string; lat: number; lon: number }>;
};
