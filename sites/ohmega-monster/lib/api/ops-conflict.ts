import { conflictFacts, EVENT_SOURCES, EVENT_TYPES, latestZones, logProvenance, provenanceText, recentEvents, type Provenance } from "@/lib/conflict";

import { abs, badRequest, enumParam, limitParam, newest, paginate, sinceParam, type ApiResult, type Args } from "./util";

// Ops over the attack log and the GNSS-interference zones (backend `conflict/` and `gnss/`; the published documents `conflict/recent.json` and `gnss/latest.json`).
// Programmatic: no model in the loop. Every response carries
// `provenance` (what kind of record, the limit of its coverage, and since when Ohmega has been collecting) and every row its own `basis` and `coverage_note`.

const ISO2 = /^[A-Za-z]{2}$/;
const SOURCE_IDS = Object.keys(EVENT_SOURCES) as (keyof typeof EVENT_SOURCES)[];

const withText = (p: Provenance) => ({ ...p, summary: provenanceText(p) });

/** Attacks, clashes and mass-violence events (and humanitarian reports) from GDELT, ACLED, UCDP and ReliefWeb in one schema. */
export async function attacksOp(a: Args): Promise<ApiResult> {
  const type = enumParam("type", a.type, EVENT_TYPES.map((t) => t.id));
  const source = enumParam("source", a.source, SOURCE_IDS);
  const coding = enumParam("coding", a.coding, ["machine", "curated", "report"] as const);
  const country = (a.country ?? "").trim().toUpperCase();
  if (country && !ISO2.test(country)) throw badRequest("country must be an ISO 3166-1 alpha-2 code");
  const since = sinceParam(a.since);
  const facts = await conflictFacts();
  const days = Math.min(Math.max(Number.parseInt(a.days ?? "14", 10) || 14, 1), facts?.days ?? 14);
  const all = await recentEvents(days);
  const collecting = facts?.since ?? null;
  const rows = all
    .filter((r) => (!type || r.type === type) && (!source || r.source === source) && (!coding || r.coding === coding) && (!country || r.country === country))
    .filter((r) => !since || r.on_date >= since.slice(0, 10))
    .map((r) => ({
      id: r.id,
      date: r.on_date,
      type: r.type,
      source: r.source,
      coding: r.coding,
      confidence: r.confidence,
      country: r.country || null,
      place: r.place || null,
      lat: r.lat,
      lon: r.lon,
      actors: [r.actor1, r.actor2].filter(Boolean),
      fatalities: r.fatalities,
      reports: r.articles,
      title: r.title || null,
      source_urls: r.urls,
      near_assets: r.assets,
      basis: r.basis,
      coverage_note: r.coverage_note,
      cite_as: abs("/intel/attacks"),
    }));
  const p = paginate(rows, limitParam(a.limit), a.cursor);
  return {
    data: {
      events: p.items,
      total: p.total,
      // `stored_in_window` counts every event Ohmega stored in the window; `total` counts the strongest rows the document carries that match the filters.
      stored_in_window: facts?.total ?? null,
      types: EVENT_TYPES,
      sources: EVENT_SOURCES,
      sources_live: Object.fromEntries(Object.entries(facts?.sources ?? {}).map(([k, v]) => [k, v.active])),
      provenance: withText(logProvenance(all, collecting)),
    },
    as_of: newest(...rows.map((r) => r.date)),
    cite_as: abs("/intel/attacks"),
    source: "conflict/recent.json",
    next_cursor: p.next_cursor,
    note:
      "Ohmega's normalised record of reported attacks and clashes. total counts what the sources reported since Ohmega began collecting (provenance.baseline_since): a minimum, never a census; the list is capped to the strongest events (curated and fatal first) and stored_in_window is the count of everything stored. ReliefWeb, ACLED and UCDP appear only once their keys are set (sources_live). " +
      "coding=machine rows (GDELT) are software readings of news text: they can duplicate, misplace or misread an event and never carry casualty figures (fatalities null). " +
      "coding=curated rows (ACLED, UCDP) are researcher-checked; coding=report rows (ReliefWeb) are published humanitarian reports without coordinates. near_assets lists ledger places within a few km: proximity, not a claim of damage.",
  };
}

/** GNSS interference zones: our own ADS-B estimate and GPSJam's file. */
export async function gnssOp(a: Args): Promise<ApiResult> {
  const source = enumParam("source", a.source, ["ohmega_adsb", "gpsjam"] as const);
  const severity = enumParam("severity", a.severity, ["low", "medium", "high"] as const);
  const flag = enumParam("flag", a.flag, ["new", "intensifying"] as const);
  const country = (a.country ?? "").trim().toUpperCase();
  if (country && !ISO2.test(country)) throw badRequest("country must be an ISO 3166-1 alpha-2 code");
  const latest = await latestZones();
  const all = latest?.zones ?? [];
  const mine = all.find((z) => z.source === "ohmega_adsb");
  const rows = all
    .filter((r) => (!source || r.source === source) && (!severity || r.severity === severity) && (!flag || r.flag === flag) && (!country || r.country === country))
    .map((r) => ({
      id: r.id,
      date: r.on_date,
      source: r.source,
      centre: { lat: r.lat, lon: r.lon },
      cell_degrees: r.size_deg,
      country: r.country || null,
      severity: r.severity,
      degraded_share: r.degraded_share,
      aircraft_observations: r.aircraft,
      flag: r.flag || null,
      gpsjam_check: r.cross_check || null,
      basis: r.basis,
      coverage_note: r.coverage_note,
      baseline_since: r.baseline_since,
      cite_as: abs("/intel/gnss"),
    }));
  const p = paginate(rows, limitParam(a.limit), a.cursor);
  const ours: Provenance = { basis: "our_estimate", coverage_note: mine?.coverage_note ?? "Ohmega's own estimate from ADS-B navigation accuracy.", baseline_since: mine?.baseline_since ?? null };
  return {
    data: { zones: p.items, total: p.total, day: latest?.day ?? null, history: latest?.history ?? [], provenance: { ohmega_adsb: withText(ours) } },
    as_of: latest?.day ?? null,
    cite_as: abs("/intel/gnss"),
    source: "gnss/latest.json",
    next_cursor: p.next_cursor,
    note:
      "Cells where an unusual share of aircraft report poor navigation accuracy (ADS-B NACp below 7), a sign of GPS jamming or spoofing, not proof of who is responsible. source=ohmega_adsb is Ohmega's own estimate " +
      "(basis our_estimate): a one-degree cell, scored from hourly samples, flagged new or intensifying against that cell's own history once a week of history exists (baseline_since says when collection began). " +
      "It is a minimum: only aircraft that broadcast ADS-B and are heard by volunteer receivers are seen, and only where Ohmega samples. source=gpsjam is GPSJam.org's independent daily file (third_party), only its highest band. " +
      "gpsjam_check says whether GPSJam shows the same cell.",
  };
}
