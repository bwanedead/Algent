import { addDays, ahead, isUnconfirmed, kindOf, todayIso, untilWords } from "./calendar";
import { claimOf } from "./daily";
import type { HudAnomaly, HudComing, HudCounter, HudData, HudLive, HudSanction } from "./globe/hud-data";
import { liveAnomalies, liveEvents, liveStats, liveSummary, type LiveStat } from "./live";
import { SOURCES, typeLabel } from "./sanctions";
import { historyOf, shortDate, statView, type Provenance } from "./stats/render";
import { hudView } from "./views";

// The /globe HUD's panel data. Today's report, the theaters with their Pulses, the Pulses that moved most, the calendar and sanctions rows and the paper
// trader are built on the worker server with the rest of the page's data (backend `views/hud.py`) and read here from the one HUD view; this module words the
// rows (labels, "in 3 days") against the viewer's day and adds the LIVE block, which stays a live read: its counters and anomaly flags change every few
// minutes, a view is rebuilt every half hour at most. Each block degrades to null / [] when its source is missing, so a panel shows "nothing yet" instead
// of an invented number. Server only (reads documents). The shapes live in lib/globe/hud-data.ts.

const ISO_RE = /^[A-Z]{2}$/;
const COMING_DAYS = 14;
const COMING_SHOWN = 10;
const SANCTIONS_SHOWN = 10;
const DAILY_LINE_MAX = 150;
const THEATER_LINE_MAX = 160;

/** Only web links reach a panel's href. */
const web = (u: string): string => (/^https?:\/\//i.test(u) ? u : "");

const median = (xs: number[]): number => {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

/** Per-day totals of one stat kind, oldest first, completed days only. */
function dayTotals(stats: LiveStat[], kind: LiveStat["kind"]): { days: number[]; periods: string[] } {
  const by = new Map<string, number>();
  for (const s of stats) if (s.kind === kind && !s.partial) by.set(s.period, (by.get(s.period) ?? 0) + s.value);
  const rows = Array.from(by.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  return { days: rows.map((e) => e[1]), periods: rows.map((e) => e[0]) };
}

type CounterIn = { key: HudCounter["key"]; statId: string; label: string; unit: string; layer?: "ships" | "aircraft" | "fires"; note?: string };

/** One counter, worded by the stats registry: our counts are minimums, and "vs usual" waits until our own history is long enough. */
function counter(i: CounterIn, t: { days: number[]; periods: string[] }, prov: Provenance | undefined): HudCounter | null {
  const { days } = t;
  if (days.length < 2) return null;
  const value = days[days.length - 1];
  const before = days.slice(-15, -1);
  const usual = before.length >= 5 ? median(before) : null;
  const pct = usual && usual > 0 ? Math.round(((value - usual) / usual) * 100) : null;
  const v = statView({ id: i.statId, value, compare: { kind: "usual", pct }, history: historyOf(t.periods), provenance: prov, layer: i.layer, note: i.note });
  return { key: i.key, label: i.label, value, text: v.text, unit: i.unit, delta: v.comparison, collecting: v.collecting, spark: days.slice(-14), href: "/live", statId: v.def.id, info: v.lines };
}

/** How much of the gate total one gate (Malacca) makes up on the latest completed day, in words for the hover. */
function dominantGate(stats: LiveStat[]): string | undefined {
  const ships = stats.filter((s) => s.kind === "ships" && !s.partial);
  const last = ships.reduce((m, s) => (s.period > m ? s.period : m), "");
  const day = ships.filter((s) => s.period === last);
  const total = day.reduce((a, s) => a + s.value, 0);
  const top = [...day].sort((a, b) => b.value - a.value)[0];
  return total > 0 && top ? `On ${shortDate(last)}, ${top.name.split(" — ")[0]} was ${Math.round((top.value / total) * 100)}% of this total.` : undefined;
}

async function liveBlock(): Promise<HudLive | null> {
  const [stats, events, anomalies, summary] = await Promise.all([liveStats(), liveEvents(), liveAnomalies(), liveSummary()]);
  const prov = summary?.provenance;
  const now = Date.now();
  const distinct = (kind: LiveStat["kind"]): number => new Set(stats.filter((s) => s.kind === kind).map((s) => s.region)).size;
  const counters = [
    counter({ key: "aircraft", statId: "mil_aircraft_peak", label: "Military aircraft, busiest moment", unit: `at once, summed over ${distinct("aircraft")} regions`, layer: "aircraft" }, dayTotals(stats, "aircraft"), prov),
    counter({ key: "ships", statId: "hud_gate_crossings", label: `Gate crossings, ${distinct("ships")} gates summed`, unit: "ships / day", layer: "ships", note: dominantGate(stats) }, dayTotals(stats, "ships"), prov),
    counter({ key: "fires", statId: "hud_fire_detections", label: `Fire detections, ${distinct("fires")} watched boxes`, unit: "per day", layer: "fires" }, dayTotals(stats, "fires"), prov),
  ].filter((c): c is HudCounter => c !== null);
  const quakes = events.filter((e) => e.kind === "quake" && e.starts_at && now - Date.parse(e.starts_at) < 86400000).length;
  const outages = events.filter((e) => e.kind === "outage" && e.ends_at === null).length;
  if (events.length > 0) {
    for (const [key, statId, label, unit, value] of [["quakes", "quakes_24h", "Quakes M4.5+", "last 24 h", quakes], ["outages", "outages_ongoing", "Outages", "ongoing", outages]] as const) {
      const v = statView({ id: statId, value });
      counters.push({ key, label, value, text: v.text, unit, delta: null, collecting: null, spark: [], href: "/live", statId, info: v.lines });
    }
  }
  const flags: HudAnomaly[] = anomalies.filter((a) => a.active).slice(0, 6).map((a) => ({
    id: a.id, sentence: a.sentence, direction: a.direction, confidence: a.confidence, ongoing: a.ends_at === null, iso: a.countries.filter((c) => ISO_RE.test(c)),
  }));
  return counters.length === 0 && flags.length === 0 ? null : { counters, anomalies: flags };
}

export async function hudData(): Promise<HudData> {
  const [view, live] = await Promise.all([hudView(), liveBlock()]);
  const h = view?.hud;
  const today = todayIso();
  const coming: HudComing[] = ahead(h?.coming ?? [], today)
    .filter((r) => r.on_date <= addDays(today, COMING_DAYS))
    .slice(0, COMING_SHOWN)
    .map((r) => ({
      date: r.on_date, end: r.end_date ?? "", title: r.title, kind: r.kind, label: kindOf(r.kind).label, iso: r.countries.map((c) => c.toUpperCase()).filter((c) => ISO_RE.test(c)),
      url: web(r.source_url), ours: isUnconfirmed(r), until: untilWords(r.on_date, today),
    }));
  const sanctions: HudSanction[] = (h?.sanctions ?? [])
    .filter((r) => r.action === "designated")
    .sort((a, b) => b.on_date.localeCompare(a.on_date))
    .slice(0, SANCTIONS_SHOWN)
    .map((r) => ({
      id: r.id, name: r.name, type: typeLabel(r.type), source: SOURCES[r.source]?.short ?? r.source, date: r.on_date,
      iso: r.countries.map((c) => c.toUpperCase()).filter((c) => ISO_RE.test(c)), programme: r.programmes[0] ?? "", url: web(r.source_url),
    }));
  return {
    asOf: h?.asOf ?? "",
    daily: h?.daily ? { ...h.daily, items: h.daily.items.map((i) => ({ ...i, text: claimOf(i.text, DAILY_LINE_MAX) })) } : null,
    theaters: (h?.theaters ?? []).map((t) => ({ ...t, line: claimOf(t.line, THEATER_LINE_MAX) })),
    pulses: h?.pulses ?? [],
    live,
    coming,
    sanctions,
    trader: h?.trader ?? null,
    tweets: null, // no published source yet: see HudTweet in lib/globe/hud-data.ts
  };
}
