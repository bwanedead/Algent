import { recordLedger } from "@/lib/record";
import { SITE_URL } from "@/lib/site";

import {
  abs, arr, badRequest, DATE_RE, docObj, enumParam, idParam, isObj, limitParam, lower, newest, notFound, objs, paginate, sinceParam, str,
  type ApiResult, type Args, type Obj,
} from "./util";

// Ops over the intelligence desk's published documents (daily, theaters, Pulses, statements, actors, briefs,
// changes, forecasts). They serve the SAME documents the human pages and /data/* read (lib/store.ts), so the API
// can never disagree with the site; nothing is re-parsed or re-derived here beyond filtering, paging and links.

export const apiUrl = (p: string): string => `${SITE_URL}/api/v1${p}`;

// ---- daily ----------------------------------------------------------------------------------------------

const DOMAIN_RE = /^[\w-]+$/;

export async function dailyOp(a: Args): Promise<ApiResult> {
  const domain = a.domain || "geopolitics";
  const date = a.date || "latest";
  if (!DOMAIN_RE.test(domain)) throw badRequest("domain must be a slug, e.g. geopolitics");
  if (date !== "latest" && !DATE_RE.test(date)) throw badRequest("date must be YYYY-MM-DD or 'latest'");
  let doc = await docObj(`data/daily/${domain}/${date}.json`);
  if (!doc && date === "latest") {
    // latest.json is a convenience copy; the intel index always names the newest dated report.
    const idx = await docObj("data/intel.json");
    const newestDay = objs(idx?.daily).find((d) => str(d.domain) === domain);
    if (newestDay) doc = await docObj(`data/daily/${domain}/${str(newestDay.date)}.json`);
  }
  if (!doc) throw notFound(`daily report ${domain}/${date}`);
  const day = str(doc.date) || date;
  return {
    data: { id: `daily:${domain}:${day}`, ...doc, cite_as: abs(str(doc.url) || `/geopolitics/${day}`), api_url: apiUrl(`/daily/${domain}/${day}`) },
    as_of: str(doc.built_at) || day,
    cite_as: abs(str(doc.url) || `/geopolitics/${day}`),
    source: "ohmega.daily/1",
    note: "Each development carries verification: 'researched' (our research established it) or 'reported' (another outlet reported it; a lead, not a finding).",
  };
}

// ---- theaters -------------------------------------------------------------------------------------------

export async function theatersOp(a: Args): Promise<ApiResult> {
  const idx = await docObj("theaters/index.json");
  const q = lower(a.q);
  const rows = objs(idx?.theaters)
    .filter((t) => (!a.domain || str(t.domain) === a.domain) && (!q || str(t.name).toLowerCase().includes(q)))
    .map((t) => ({
      id: str(t.theater_id),
      ...t,
      cite_as: abs(`/intel/theaters/${str(t.theater_id)}`),
      api_url: apiUrl(`/theaters/${str(t.theater_id)}`),
    }));
  const p = paginate(rows, limitParam(a.limit), a.cursor);
  return {
    data: { theaters: p.items, total: p.total },
    as_of: str(idx?.built_at) || null,
    cite_as: abs("/intel/theaters"),
    source: "ohmega.dossier.index/1",
    next_cursor: p.next_cursor,
    note: "heat is how much a theater is in the news, not how bad things are.",
  };
}

export async function theaterOp(a: Args): Promise<ApiResult> {
  const id = idParam("id", a.id);
  const doc = id === "index" ? null : await docObj(`theaters/${id}.json`);
  if (!doc) throw notFound(`theater ${id}`);
  const { map: _map, ...rest } = doc; // the drawing spec is presentation; places[] carries the coordinates
  const cite = abs(`/intel/theaters/${id}`);
  return {
    data: { id, ...rest, cite_as: cite, api_url: apiUrl(`/theaters/${id}`) },
    as_of: str(doc.built_at) || null,
    cite_as: cite,
    source: "ohmega.dossier/1",
    note: "timeline[] and on_record[] items carry their own verification and source URLs.",
  };
}

// ---- briefs ---------------------------------------------------------------------------------------------

export async function briefOp(a: Args): Promise<ApiResult> {
  const slug = idParam("slug", a.slug);
  const doc = await docObj(`data/briefs/${slug}.json`);
  if (!doc) throw notFound(`brief ${slug}`);
  const cite = abs(str(doc.url) || `/intel/briefs/${slug}`);
  return { data: { id: slug, ...doc, cite_as: cite }, as_of: str(doc.as_of) || null, cite_as: cite, source: "ohmega.brief/1" };
}

// ---- Pulses ---------------------------------------------------------------------------------------------

const BANDS = ["calm", "elevated", "severe", "critical", "unassessed"] as const;

export async function pulsesOp(a: Args): Promise<ApiResult> {
  const band = enumParam("band", a.band, BANDS);
  const status = enumParam("status", a.status, ["experimental", "active", "dormant"] as const);
  const q = lower(a.q);
  const doc = await docObj("data/pulses.json");
  if (!doc) throw notFound("pulse list");
  const rows = objs(doc.pulses)
    .filter((p) => (!band || str(p.band) === band) && (!status || str(p.status) === status))
    .filter((p) => !q || `${str(p.name)} ${str(p.question)} ${str(p.situation)}`.toLowerCase().includes(q))
    .map((p) => {
      const { history, ...rest } = p; // the trace lives on /pulses/{id}
      return { ...rest, history_points: arr(history).length, cite_as: abs("/pulses"), api_url: apiUrl(`/pulses/${str(p.id)}`) };
    });
  const p = paginate(rows, limitParam(a.limit), a.cursor);
  return {
    data: { pulses: p.items, total: p.total },
    as_of: str(doc.built_at) || null,
    cite_as: abs("/pulses"),
    source: "ohmega.pulses/1",
    next_cursor: p.next_cursor,
    note: "A Pulse is a persistent 0-100 reading of one question (0 calm end, 100 extreme end, see low_end/high_end): our reading as of last_assessed, still calibrating, not a measurement.",
  };
}

export async function pulseOp(a: Args): Promise<ApiResult> {
  const id = idParam("id", a.id);
  const doc = await docObj(`data/pulses/${id}.json`);
  if (!doc) throw notFound(`pulse ${id}`);
  return {
    data: { ...doc, cite_as: abs("/pulses"), api_url: apiUrl(`/pulses/${id}`) },
    as_of: str(doc.last_assessed) || null,
    cite_as: abs("/pulses"),
    source: "ohmega.pulse/1",
    note: "readings[] is the full trace. mode 'audit' readings are blind checks from the evidence alone: kept as provenance, they never move the Pulse (moves_pulse=false).",
  };
}

// ---- statements (the on-the-record ledger) ---------------------------------------------------------------

export async function statementsOp(a: Args): Promise<ApiResult> {
  const since = sinceParam(a.since);
  const who = lower(a.actor);
  const signal = lower(a.signal);
  const ledger = await recordLedger();
  if (!ledger) throw notFound("statements ledger");
  const iso = /^[a-z]{2}$/.test(who) ? who.toUpperCase() : "";
  const rows = ledger.statements
    .filter((s) => !since || s.date >= since)
    .filter((s) => !signal || s.signal.toLowerCase() === signal)
    .filter(
      (s) =>
        !who ||
        (iso !== "" && (s.iso2 === iso || s.about_iso2.includes(iso))) ||
        `${s.speaker} ${s.affiliation}`.toLowerCase().includes(who) ||
        s.about.some((x) => x.toLowerCase().includes(who)),
    )
    .map((s) => ({ ...s, source_url: s.url, cite_as: abs("/intel/record") }));
  const p = paginate(rows, limitParam(a.limit), a.cursor);
  return {
    data: { statements: p.items, total: p.total, window_days: ledger.window_days },
    as_of: ledger.as_of || null,
    cite_as: abs("/intel/record"),
    source: "ohmega.record/1",
    next_cursor: p.next_cursor,
    note: "A statement proves it was SAID, not that it is true. quote is exact words (validated against the source); paraphrase otherwise. stance -2 hostile .. +2 conciliatory toward 'about'.",
  };
}

// ---- actors ---------------------------------------------------------------------------------------------

export async function actorsOp(a: Args): Promise<ApiResult> {
  const idx = await docObj("data/actors/index.json");
  if (!idx) throw notFound("actor list");
  const q = lower(a.q);
  const rows = objs(idx.actors)
    .filter((x) => !q || `${str(x.name)} ${str(x.iso2)}`.toLowerCase().includes(q))
    .map((x) => ({ id: str(x.iso2), ...x, cite_as: abs(`/intel/actors/${str(x.iso2)}`), api_url: apiUrl(`/actors/${str(x.iso2)}`) }));
  const p = paginate(rows, limitParam(a.limit), a.cursor);
  return {
    data: { actors: p.items, total: p.total },
    as_of: str(idx.data_as_of) || null,
    cite_as: abs("/intel/actors"),
    source: "ohmega.actor.index/1",
    next_cursor: p.next_cursor,
  };
}

export async function actorOp(a: Args): Promise<ApiResult> {
  const iso = (a.iso ?? "").toUpperCase();
  if (!/^[A-Z]{2}$/.test(iso)) throw badRequest("iso must be an ISO 3166-1 alpha-2 code, e.g. IR");
  const doc = await docObj(`data/actors/${iso}.json`);
  if (!doc) throw notFound(`actor ${iso}`);
  const cite = abs(`/intel/actors/${iso}`);
  return {
    data: { id: iso, ...doc, cite_as: cite, api_url: apiUrl(`/actors/${iso}`) },
    as_of: str(doc.data_as_of) || null,
    cite_as: cite,
    source: "ohmega.actor/1",
    note: "Figures carry their own year and source; credits[] lists licences.",
  };
}

// ---- changes and forecasts (passthrough with paging) ----------------------------------------------------

export async function changesOp(a: Args): Promise<ApiResult> {
  const since = sinceParam(a.since);
  const doc = await docObj("data/changes.json");
  if (!doc) throw notFound("changes feed");
  const rows = objs(doc.events).filter((e) => (!since || str(e.at) >= since) && (!a.type || str(e.type) === a.type));
  const p = paginate(rows, limitParam(a.limit), a.cursor);
  return {
    data: { window_days: doc.window_days ?? null, events: p.items, total: p.total },
    as_of: str(doc.as_of) || null,
    cite_as: abs("/intel"),
    source: "ohmega.changes/1",
    next_cursor: p.next_cursor,
  };
}

export async function forecastsOp(a: Args): Promise<ApiResult> {
  const status = enumParam("status", a.status, ["open", "yes", "no", "void"] as const);
  const doc = await docObj("data/forecasts.json");
  if (!doc) throw notFound("forecasts");
  const rows = objs(doc.forecasts).filter((f) => !status || str(f.status) === status);
  const p = paginate(rows, limitParam(a.limit), a.cursor);
  return {
    data: { scorecard: isObj(doc.scorecard) ? (doc.scorecard as Obj) : null, forecasts: p.items, total: p.total },
    as_of: str(doc.as_of) || null,
    cite_as: abs("/intel"),
    source: "ohmega.forecasts/1",
    next_cursor: p.next_cursor,
    note: "Forecasts are probabilities (percent), scored publicly (Brier: lower is better, 0.25 is a coin flip). Misses stay in the record.",
  };
}

/** Freshest timestamp the desk has published (the changes feed's as_of), for the index. */
export async function deskAsOf(): Promise<string | null> {
  const doc = await docObj("data/changes.json");
  const idx = await docObj("data/intel.json");
  return newest(str(doc?.as_of), str(idx?.built_at));
}
