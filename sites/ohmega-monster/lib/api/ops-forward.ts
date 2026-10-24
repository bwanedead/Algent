import { addDays, calendarItems, KINDS, TOPICS, todayIso } from "@/lib/calendar";
import { recentSanctions, SOURCES, TYPES, type SanctionsSource } from "@/lib/sanctions";

import { abs, badRequest, enumParam, limitParam, newest, paginate, sinceParam, type ApiResult, type Args } from "./util";

// Ops over the forward-looking and list-change feeds: the calendar (dated things ahead) and sanctions designations. Both are programmatic
// (backend `lookahead/` and `sanctions/`, migration 012): no model in the loop, a source URL on every row.

const KIND_IDS = KINDS.map((k) => k.id);
const TOPIC_IDS = TOPICS.map((t) => t.id);
const GRADES = ["official", "announced", "estimated", "unconfirmed"] as const;
const ISO2 = /^[A-Za-z]{2}$/;

/** Dated things ahead. Every row has a topic, an importance (1 routine .. 3 major), a grade (official | announced | estimated | unconfirmed) and every
 *  source that listed it. Routine rows (the weekly stock reports, UN Security Council meetings) are left out unless `routine=true`. */
export async function calendarOp(a: Args): Promise<ApiResult> {
  const kind = enumParam("kind", a.kind, KIND_IDS);
  const topic = enumParam("topic", a.topic, TOPIC_IDS);
  const grade = enumParam("grade", a.grade, GRADES);
  const confidence = enumParam("confidence", a.confidence, ["high", "medium", "low"] as const);
  const country = (a.country ?? "").trim().toUpperCase();
  if (country && !ISO2.test(country)) throw badRequest("country must be an ISO 3166-1 alpha-2 code");
  const situation = (a.situation ?? "").trim();
  const minImportance = Math.min(Math.max(Number.parseInt(a.min_importance ?? (a.routine === "true" ? "1" : "2"), 10) || 1, 1), 3);
  const days = Math.min(Math.max(Number.parseInt(a.days ?? "45", 10) || 45, 1), 180);
  const today = todayIso();
  const rows = (await calendarItems(days))
    .filter((r) => r.on_date <= addDays(today, days))
    .filter((r) => (!kind || r.kind === kind) && (!topic || r.topic === topic) && (!grade || r.grade === grade) && (!confidence || r.confidence === confidence))
    .filter((r) => (!country || r.countries.includes(country)) && (!situation || r.situations.includes(situation)) && r.importance >= minImportance)
    .map((r) => ({
      id: r.id,
      date: r.on_date,
      end_date: r.end_date,
      title: r.title,
      kind: r.kind,
      topic: r.topic,
      importance: r.importance,
      grade: r.grade,
      countries: r.countries,
      theater_ids: r.theaters,
      situation_ids: r.situations,
      confidence: r.confidence,
      provenance: r.provenance,
      source: r.source,
      source_url: r.source_url,
      sources: r.sources,
      cite_as: abs("/calendar"),
    }));
  const p = paginate(rows, limitParam(a.limit), a.cursor);
  return {
    data: { items: p.items, total: p.total, kinds: KIND_IDS, topics: TOPIC_IDS, from: today, days },
    as_of: today,
    cite_as: abs("/calendar"),
    source: "calendar_items",
    next_cursor: p.next_cursor,
    note:
      "Dated items ahead, soonest first, merged across sources. importance: 3 major, 2 notable, 1 routine (hidden unless routine=true or min_importance=1). " +
      "grade: official = the body's own schedule; announced = compiled from announcements or company-confirmed; estimated = generated from a published rule or a projection; " +
      "unconfirmed (provenance ohmega_derived) = a date from Ohmega's own earlier reports or watches. confidence is the older three-level form of grade. " +
      "A date is a plan, not an outcome: dates move and meetings are cancelled.",
  };
}

/** Designations and delistings on the OFAC SDN, UK and EU lists, found by diffing each list against its previous copy. */
export async function sanctionsOp(a: Args): Promise<ApiResult> {
  const source = enumParam("source", a.source, Object.keys(SOURCES) as SanctionsSource[]);
  const action = enumParam("action", a.action, ["designated", "delisted"] as const);
  const type = enumParam("type", a.type, TYPES.map((t) => t.id));
  const country = (a.country ?? "").trim().toUpperCase();
  if (country && !ISO2.test(country)) throw badRequest("country must be an ISO 3166-1 alpha-2 code");
  const since = sinceParam(a.since);
  const rows = (await recentSanctions(180))
    .filter((r) => (!source || r.source === source) && (!action || r.action === action) && (!type || r.type === type) && (!country || r.countries.includes(country)))
    .filter((r) => !since || r.on_date >= since.slice(0, 10))
    .map((r) => ({
      id: r.id,
      list: r.source,
      action: r.action,
      date: r.on_date,
      first_seen: r.observed_on,
      name: r.name,
      type: r.type,
      programmes: r.programmes,
      countries: r.countries,
      imo: r.imo || null,
      flag: r.flag || null,
      owner: r.owner || null,
      list_dated: r.baseline,
      source_url: r.source_url,
      cite_as: abs("/intel/sanctions"),
    }));
  const p = paginate(rows, limitParam(a.limit), a.cursor);
  return {
    data: { events: p.items, total: p.total, lists: SOURCES },
    as_of: newest(...rows.map((r) => r.first_seen)),
    cite_as: abs("/intel/sanctions"),
    source: "sanctions_events",
    verification: "official_list",
    next_cursor: p.next_cursor,
    note:
      "Each row is a change between two copies of an official list (US Treasury OFAC SDN, UK Sanctions List, EU consolidated financial sanctions list), read every six hours. " +
      "date is the designation date when the list states a recent one, otherwise the day Ohmega first saw the change (first_seen). list_dated=true: found when we first read a list that dates its own entries. " +
      "The US list carries no dates, so its changes start from our first copy. A listing is an administrative act of the publishing government, not a finding of guilt.",
  };
}
