import { addDays, ahead, calendarItems, isUnconfirmed, kindOf, todayIso, untilWords } from "./calendar";
import { allDailyDates, claimOf, daily, dayHref, theaterAnchor, type Daily } from "./daily";
import { entityIndex, textLinker } from "./entities";
import { dailyMentions } from "./globe-mentions";
import type { HudAnomaly, HudComing, HudCounter, HudData, HudDaily, HudLive, HudPulse, HudSanction, HudTheater, HudTrader } from "./globe/hud-data";
import { latestSnapshot, severitySorted, type Pulse } from "./intel";
import { liveAnomalies, liveEvents, liveStats, liveSummary, type LiveStat } from "./live";
import { recentSanctions, SOURCES, typeLabel } from "./sanctions";
import { historyOf, shortDate, statView, type Provenance } from "./stats/render";
import { trackRecord } from "./track-record";

// Builds the /globe HUD's panel data from what the site already publishes (no model calls, no new documents). Each block is built on its
// own and degrades to null / [] when its source is missing, so a panel shows "nothing yet" instead of an invented number.
// Server only (reads documents). The shapes live in lib/globe/hud-data.ts.

const DOMAIN = "geopolitics";
const BASE = "/daily/geopolitics";
const ISO_RE = /^[A-Z]{2}$/;
const DAILY_ITEMS = 10;
const PULSES_SHOWN = 12;
const HISTORY_POINTS = 30;
const COMING_DAYS = 14;
const COMING_SHOWN = 10;
const SANCTIONS_SHOWN = 10;
const TIES_PER_THEATER = 6;
const CURVE_DAYS = 90;

/** Only web links reach a panel's href. */
const web = (u: string): string => (/^https?:\/\//i.test(u) ? u : "");

const median = (xs: number[]): number => {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

function toHudPulse(p: Pulse): HudPulse {
  return {
    id: p.id, title: p.title || p.name, band: p.band, position: p.position, change7d: p.velocity_7d,
    history: p.history.slice(-HISTORY_POINTS).map((h) => h.position), iso: p.actors_iso2.filter((c) => ISO_RE.test(c)), href: `/pulses#pulse-${p.id}`,
  };
}

/** Today's report as theme-dotted lines: each theater's headline first, then developments, up to DAILY_ITEMS. */
function dailyBlock(d: Daily, dates: string[], linker: Awaited<ReturnType<typeof textLinker>>): HudDaily {
  const mentions = dailyMentions(d, dates, linker);
  const pick = [...mentions.filter((m) => m.kind === "section"), ...mentions.filter((m) => m.kind === "development")].slice(0, DAILY_ITEMS);
  return {
    date: d.date,
    headline: d.headline,
    items: pick.map((m) => ({ theme: m.theme, text: m.text, href: m.href, date: m.date, kind: m.kind, iso: m.isos })),
  };
}

function theatersBlock(d: Daily, dates: string[], ties: Map<string, Map<string, number>>, pulseById: Map<string, HudPulse>): HudTheater[] {
  const out: HudTheater[] = [];
  d.theaters.forEach((t, i) => {
    if (t.kind !== "section") return;
    const iso = Array.from(ties.get(t.theater_id) ?? []).sort((a, b) => b[1] - a[1]).slice(0, TIES_PER_THEATER).map(([c]) => c);
    out.push({
      id: t.theater_id, name: t.name, heat: t.temperature.heat, trend: t.temperature.trend, dir: t.escalation.direction, pace: t.escalation.pace,
      line: t.headline || claimOf(t.bottom_line, 160), href: `${dayHref(BASE, d.date, dates)}#${theaterAnchor(t, i)}`, iso,
      pulses: t.pulses.map((p) => pulseById.get(p.id) ?? { id: p.id, title: p.title || p.name, band: p.band, position: p.position, change7d: p.change_7d, history: [], iso: p.actors_iso2, href: `/pulses#pulse-${p.id}` }),
    });
  });
  return out.sort((a, b) => b.heat - a.heat);
}

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

async function comingBlock(): Promise<HudComing[]> {
  const today = todayIso();
  const rows = ahead(await calendarItems(COMING_DAYS), today).filter((r) => r.on_date <= addDays(today, COMING_DAYS));
  return rows.slice(0, COMING_SHOWN).map((r) => ({
    date: r.on_date, end: r.end_date ?? "", title: r.title, kind: r.kind, label: kindOf(r.kind).label, iso: r.countries.map((c) => c.toUpperCase()).filter((c) => ISO_RE.test(c)),
    url: web(r.source_url), ours: isUnconfirmed(r), until: untilWords(r.on_date, today),
  }));
}

async function sanctionsBlock(): Promise<HudSanction[]> {
  const rows = (await recentSanctions(21, 300)).filter((r) => r.action === "designated");
  return rows.sort((a, b) => b.on_date.localeCompare(a.on_date)).slice(0, SANCTIONS_SHOWN).map((r) => ({
    id: r.id, name: r.name, type: typeLabel(r.type), source: SOURCES[r.source]?.short ?? r.source, date: r.on_date,
    iso: r.countries.map((c) => c.toUpperCase()).filter((c) => ISO_RE.test(c)), programme: r.programmes[0] ?? "", url: web(r.source_url),
  }));
}

async function traderBlock(): Promise<HudTrader | null> {
  const rec = await trackRecord();
  const t = rec?.trader;
  if (!rec || !t) return null;
  const curve = t.curve.filter((c): c is typeof c & { trader: number } => c.trader !== null).slice(-CURVE_DAYS).map((c) => ({ day: c.day, flat: c.flat, trader: c.trader }));
  if (curve.length === 0) return null;
  return {
    asOf: rec.as_of, bankroll: t.limits.bankroll, equity: t.summary.equity, pnl: t.summary.pnl, open: t.summary.open, curve,
    positions: [...t.open_positions].sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl)).slice(0, 6).map((p) => ({ question: p.question, side: p.side, pnl: p.pnl, value: p.value, url: p.url })),
  };
}

export async function hudData(): Promise<HudData> {
  const [dates, idx, linker, snap] = await Promise.all([allDailyDates(DOMAIN), entityIndex(), textLinker(), latestSnapshot()]);
  const top = dates[0] ? await daily(DOMAIN, dates[0]) : null;
  const pulses = severitySorted(snap).flatMap((s) => s.pulses).filter((p) => p.position !== null && p.history.length >= 2);
  const pulseById = new Map(pulses.map((p) => [p.id, toHudPulse(p)]));
  const movers = [...pulses].sort((a, b) => Math.abs(b.velocity_7d ?? 0) - Math.abs(a.velocity_7d ?? 0)).slice(0, PULSES_SHOWN).map(toHudPulse);
  const [live, coming, sanctions, trader] = await Promise.all([liveBlock(), comingBlock(), sanctionsBlock(), traderBlock()]);
  return {
    asOf: top?.date ?? "",
    daily: top ? dailyBlock(top, dates, linker) : null,
    theaters: top ? theatersBlock(top, dates, idx.ties, pulseById) : [],
    pulses: movers,
    live, coming, sanctions, trader,
    tweets: null, // no published source yet: see HudTweet in lib/globe/hud-data.ts
  };
}
