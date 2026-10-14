// What the geopolitics daily shows live: military aircraft, tankers and military / law-enforcement vessels near a theater, and nothing
// else (no fires, quakes or outages: those stay on /live). Pure and client-safe: the groups, the filter over /live's decoded objects
// (entities.ts), the per-group cap and the plain-words summary. Fetching is useTheaterObjects.ts; drawing is objectLayers.ts.

import { AIR_KINDS, SHIP_CLASSES, type Entity } from "./entities";

export type Group = "air" | "tanker" | "navy";
export type Obj = { group: Group; e: Entity };
export type Totals = Record<Group, number>;

/** Colours come from /live's own class table, so a tanker is the same amber on both. */
export const GROUPS: { key: Group; one: string; many: string; color: string }[] = [
  { key: "air", one: "military aircraft", many: "military aircraft", color: AIR_KINDS[0].color },
  { key: "tanker", one: "tanker", many: "tankers", color: SHIP_CLASSES[0].color },
  { key: "navy", one: "military/law-enforcement vessel", many: "military/law-enforcement vessels", color: SHIP_CLASSES[4].color },
];

/** At most this many of one group are drawn (the newest reports); the counts in the strip are always the true totals. */
export const MAX_PER_GROUP = 250;

/** The group an object belongs to, or null when it is not one of the three kinds the daily shows. Aircraft: any class above civil
 *  (military, tanker, surveillance, airlift, fighter or bomber); ships: class tanker or military and law enforcement. */
export function groupOf(e: Entity): Group | null {
  if (e.kind === "air") return e.cls > 0 ? "air" : null;
  return e.cls === 0 ? "tanker" : e.cls === 4 ? "navy" : null;
}

export const EMPTY_TOTALS: Totals = { air: 0, tanker: 0, navy: 0 };
export type Shaped = { objs: Obj[]; totals: Totals };
export const NO_OBJECTS: Shaped = { objs: [], totals: EMPTY_TOTALS };

/** True totals per group, and the objects to draw: each group's newest `MAX_PER_GROUP`. */
export function shape(all: Obj[]): Shaped {
  const totals: Totals = { air: 0, tanker: 0, navy: 0 };
  const by: Record<Group, Obj[]> = { air: [], tanker: [], navy: [] };
  for (const o of all) {
    totals[o.group]++;
    by[o.group].push(o);
  }
  const objs = GROUPS.flatMap((g) => by[g.key].sort((a, b) => b.e.ts - a.e.ts).slice(0, MAX_PER_GROUP));
  return { objs, totals };
}

/** "3 military aircraft", "1 tanker": the strip's line for one group. */
export const countText = (g: (typeof GROUPS)[number], n: number) => `${n.toLocaleString("en-GB")} ${n === 1 ? g.one : g.many}`;

/** [west, south, east, north] widened by a tenth of its size on each side (at least half a degree): ships and aircraft just outside the
 *  frame are still "near" the theater. */
export function withMargin(b: number[]): [number, number, number, number] {
  const dx = Math.max(0.5, (b[2] - b[0]) * 0.1);
  const dy = Math.max(0.5, (b[3] - b[1]) * 0.1);
  return [b[0] - dx, b[1] - dy, b[2] + dx, b[3] + dy];
}
