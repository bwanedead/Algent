import { liveEvents, liveStats, type LiveKind, type LiveStat } from "@/lib/live";

import { apiUrl } from "./ops-desk";
import { abs, docObj, enumParam, idParam, isObj, limitParam, newest, notFound, objs, paginate, sinceParam, str, type ApiResult, type Args, type Obj } from "./util";

// Ops over the numbers layer: instruments (measured series) and live events. Both are programmatic data with a
// source URL on every row and no model in the loop (docs/architecture/instruments.md, the /live page).

// ---- instruments ----------------------------------------------------------------------------------------
// Two homes today: the trackers the latest daily report carries (numbers.trackers, id = the catalog series id,
// with changes and "unusual" flags) and our own daily live series (live_stats: ship counts through chokepoints).

type Tracker = Obj & { id: string; theater_ids: string[] };

async function dailyTrackers(): Promise<Tracker[]> {
  const doc = await docObj("data/daily/geopolitics/latest.json");
  const byId = new Map<string, Tracker>();
  const walk = (t: Obj) => {
    const numbers = isObj(t.numbers) ? t.numbers : null;
    for (const tr of objs(numbers?.trackers)) {
      const id = str(tr.id);
      if (!id) continue;
      const have = byId.get(id);
      if (have) have.theater_ids.push(str(t.theater_id));
      else byId.set(id, { ...tr, id, theater_ids: [str(t.theater_id)] });
    }
    for (const u of objs(t.updates)) walk(u);
  };
  for (const t of objs(doc?.theaters)) walk(t);
  return Array.from(byId.values());
}

function liveSeries(stats: LiveStat[]): Map<string, LiveStat[]> {
  const by = new Map<string, LiveStat[]>();
  for (const s of stats) by.set(s.series_id, [...(by.get(s.series_id) ?? []), s]);
  Array.from(by.values()).forEach((rows) => rows.sort((a, b) => a.period.localeCompare(b.period)));
  return by;
}

export async function instrumentsOp(a: Args): Promise<ApiResult> {
  const [trackers, stats] = await Promise.all([dailyTrackers(), liveStats()]);
  const rows: Obj[] = trackers.map((t) => ({
    id: t.id,
    name: str(t.name),
    unit: str(t.unit),
    kind: "tracker",
    value: t.value ?? null,
    as_of: str(t.as_of),
    status: str(t.status),
    unusual: t.unusual === true,
    source: str(t.source),
    source_url: str(t.source_url) || null,
    cite_as: str(t.source_url) || abs("/geopolitics"),
    api_url: apiUrl(`/instruments/${t.id}`),
  }));
  for (const [id, series] of Array.from(liveSeries(stats).entries())) {
    const last = series[series.length - 1];
    rows.push({
      id,
      name: last.name,
      unit: last.unit,
      kind: "live_series",
      value: last.value,
      as_of: last.period,
      status: last.partial ? "partial_day" : "current",
      unusual: false,
      source: "Ohmega live feeds",
      source_url: last.source_url || null,
      cite_as: abs("/live"),
      api_url: apiUrl(`/instruments/${id}`),
    });
  }
  const p = paginate(rows, limitParam(a.limit), a.cursor);
  return {
    data: { instruments: p.items, total: p.total },
    as_of: newest(...rows.map((r) => str(r.as_of))),
    cite_as: abs("/geopolitics"),
    source: "ohmega.instruments",
    verification: "measured",
    next_cursor: p.next_cursor,
    note: "Measured series, no model in the loop. 'unusual' = outside the series' own history. A 'partial_day' value is still being counted.",
  };
}

export async function instrumentOp(a: Args): Promise<ApiResult> {
  const id = idParam("id", a.id);
  const tracker = (await dailyTrackers()).find((t) => t.id === id);
  if (tracker) {
    return {
      data: { ...tracker, cite_as: str(tracker.source_url) || abs("/geopolitics"), api_url: apiUrl(`/instruments/${id}`) },
      as_of: str(tracker.as_of) || null,
      cite_as: str(tracker.source_url) || abs("/geopolitics"),
      source: "ohmega.daily/1#numbers.trackers",
      verification: "measured",
      note: "changes{} are from -> to over each horizon; spark[] is the recent series (oldest first). An empty source_url marks an internal series: shown, never cited.",
    };
  }
  const series = liveSeries(await liveStats()).get(id);
  if (!series || series.length === 0) throw notFound(`instrument ${id}`);
  const last = series[series.length - 1];
  return {
    data: {
      id,
      name: last.name,
      unit: last.unit,
      kind: "live_series",
      region: last.region,
      source_url: last.source_url || null,
      points: series.map((s) => ({ period: s.period, value: s.value, partial: s.partial })),
      cite_as: abs("/live"),
      api_url: apiUrl(`/instruments/${id}`),
    },
    as_of: last.period,
    cite_as: abs("/live"),
    source: "live_stats",
    verification: "measured",
    note: "Our own daily counts from public live feeds (last ~45 days). partial=true is the day still being counted: never read it as a collapse.",
  };
}

// ---- live events ----------------------------------------------------------------------------------------

const KINDS: readonly LiveKind[] = ["outage", "quake", "aircraft", "fire"];

export async function liveEventsOp(a: Args): Promise<ApiResult> {
  const kind = enumParam("kind", a.kind, KINDS);
  const severity = enumParam("severity", a.severity, ["info", "notable", "major"] as const);
  const since = sinceParam(a.since);
  const events = (await liveEvents())
    .filter((e) => (!kind || e.kind === kind) && (!severity || e.severity === severity))
    .filter((e) => !since || (e.starts_at ?? e.updated_at ?? "") >= since)
    .map((e) => ({
      id: e.id,
      kind: e.kind,
      title: e.title,
      detail: e.detail,
      severity: e.severity,
      lat: e.lat,
      lon: e.lon,
      countries: e.countries,
      starts_at: e.starts_at,
      ends_at: e.ends_at,
      ongoing: e.ends_at === null,
      source: e.source,
      source_url: e.source_url,
      updated_at: e.updated_at,
      cite_as: abs("/live"),
    }));
  const p = paginate(events, limitParam(a.limit), a.cursor);
  return {
    data: { events: p.items, total: p.total, kinds: KINDS },
    as_of: newest(...events.map((e) => e.updated_at)),
    cite_as: abs("/live"),
    source: "live_events",
    verification: "feed_reported",
    next_cursor: p.next_cursor,
    note: "Current events from public live feeds (outage monitors, USGS, aircraft and fire feeds), relayed with their source_url. Not independently verified by Ohmega.",
  };
}
