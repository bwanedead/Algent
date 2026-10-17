import { KIND_LABEL, KIND_MEANING, KIND_ORDER, flagsOf, maritimeEvents, tally } from "@/lib/maritime";

import { abs, badRequest, enumParam, limitParam, newest, paginate, sinceParam, type ApiResult, type Args } from "./util";

// Op over vessel behaviour events (backend `maritime/`, migration 013): AIS gaps, ship-to-ship encounters, identity changes, sanctioned
// vessels seen and loitering over sensitive infrastructure. Ohmega's own analysis of the AIS it hears: provenance ohmega_derived, a reason and
// the evidence points on every row.

const ISO2 = /^[A-Za-z]{2}$/;

export async function maritimeOp(a: Args): Promise<ApiResult> {
  const kind = enumParam("kind", a.kind, KIND_ORDER);
  const active = enumParam("active", a.active, ["true", "false"] as const);
  const flag = (a.flag ?? "").trim().toUpperCase();
  if (flag && !ISO2.test(flag)) throw badRequest("flag must be an ISO 3166-1 alpha-2 code");
  const area = (a.area ?? "").trim().toLowerCase();
  const imo = (a.imo ?? "").trim();
  if (imo && !/^\d{7}$/.test(imo)) throw badRequest("imo must be a 7-digit IMO number");
  const mmsi = (a.mmsi ?? "").trim();
  if (mmsi && !/^\d{9}$/.test(mmsi)) throw badRequest("mmsi must be a 9-digit MMSI");
  const min = a.min_confidence === undefined || a.min_confidence === "" ? 0 : Number(a.min_confidence);
  if (!Number.isFinite(min) || min < 0 || min > 1) throw badRequest("min_confidence must be a number from 0 to 1");
  const since = sinceParam(a.since);
  const all = await maritimeEvents();
  const rows = all
    .filter((e) => (!kind || e.kind === kind) && (!active || String(e.active) === active) && (!flag || flagsOf(e).includes(flag)))
    .filter((e) => !area || e.area.toLowerCase().includes(area) || e.countries.some((c) => c.toLowerCase() === area))
    .filter((e) => (!imo || e.imo === imo) && (!mmsi || String(e.mmsi) === mmsi || String(e.mmsi2) === mmsi))
    .filter((e) => e.confidence >= min && (!since || e.started_at >= since))
    .map((e) => ({
      id: e.id,
      kind: e.kind,
      summary: e.summary,
      why_flagged: e.rationale,
      confidence: e.confidence,
      state: e.state,
      ongoing: e.ended_at === null,
      started_at: e.started_at,
      ended_at: e.ended_at,
      last_seen: e.last_seen,
      vessel: { name: e.name || null, imo: e.imo || null, mmsi: e.mmsi, flag: e.flag || null, ship_class: e.ship_class || null },
      partner: e.mmsi2 ? { name: e.name2 || null, mmsi: e.mmsi2, flag: e.flag2 || null } : null,
      place: { lat: e.lat, lon: e.lon, area: e.area || null, countries: e.countries },
      detail: e.detail,
      evidence: e.evidence.map(([ts, lat, lon, kn, note]) => ({ at: new Date(ts * 1000).toISOString(), lat, lon, knots: kn >= 0 ? kn : null, note: note || null })),
      provenance: e.provenance,
      updated_at: e.updated_at,
      cite_as: abs("/intel/maritime"),
    }));
  const p = paginate(rows, limitParam(a.limit), a.cursor);
  return {
    data: {
      events: p.items,
      total: p.total,
      kinds: KIND_ORDER.map((k) => ({ id: k, label: KIND_LABEL[k], meaning: KIND_MEANING[k] })),
      by_kind: tally(all, (e) => e.kind),
      by_flag: tally(all, flagsOf).slice(0, 25),
    },
    as_of: newest(...rows.map((r) => r.updated_at)),
    cite_as: abs("/intel/maritime"),
    source: "maritime_events",
    verification: "ohmega_derived",
    next_cursor: p.next_cursor,
    note:
      "Ohmega analysis (provenance ohmega_derived) of the ship positions it hears over AIS, not something a source reported. Each row is a pattern seen, never a finding of intent: " +
      "a silence, an encounter, a rename or a long dwell all have innocent explanations. why_flagged gives the numbers behind the flag and confidence is 0..1. " +
      "AIS gaps are only reported where other ships kept being heard (a ship that left receiver coverage is not 'going dark'); ports, anchorage crowds and our own outages are screened out. " +
      "A sanctioned-vessel match rests on the IMO number (high confidence) or on exact name plus flag state (medium). Cable and pipeline zones are approximate proxies. " +
      "Ended events stay for 30 days. evidence points are what AIS reported (time, position, speed).",
  };
}
