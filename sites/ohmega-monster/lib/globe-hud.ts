import { addDays, ahead, calendarItems, kindOf, todayIso, untilWords } from "./calendar";
import { allDailyDates, claimOf, daily, dayHref, theaterAnchor, type Daily } from "./daily";
import { entityIndex, textLinker } from "./entities";
import { dailyMentions } from "./globe-mentions";
import type { HudAnomaly, HudComing, HudCounter, HudData, HudDaily, HudLive, HudPulse, HudSanction, HudTheater, HudTrader } from "./globe/hud-data";
import { latestSnapshot, severitySorted, type Pulse } from "./intel";
import { liveAnomalies, liveEvents, liveStats, type LiveStat } from "./live";
import { recentSanctions, SOURCES, typeLabel } from "./sanctions";
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
function dayTotals(stats: LiveStat[], kind: LiveStat["kind"]): number[] {
  const by = new Map<string, number>();
  for (const s of stats) if (s.kind === kind && !s.partial) by.set(s.period, (by.get(s.period) ?? 0) + s.value);
  return Array.from(by.entries()).sort((a, b) => a[0].localeCompare(b[0])).map((e) => e[1]);
}

function counter(key: HudCounter["key"], label: string, unit: string, days: number[]): HudCounter | null {
  if (days.length < 2) return null;
  const value = days[days.length - 1];
  const before = days.slice(-15, -1);
  const usual = before.length >= 5 ? median(before) : null;
  return { key, label, value, unit, pct: usual && usual > 0 ? Math.round(((value - usual) / usual) * 100) : null, spark: days.slice(-14), href: "/live" };
}

async function liveBlock(): Promise<HudLive | null> {
  const [stats, events, anomalies] = await Promise.all([liveStats(), liveEvents(), liveAnomalies()]);
  const now = Date.now();
  const counters = [
    counter("aircraft", "Military aircraft", "seen / day", dayTotals(stats, "aircraft")),
    counter("ships", "Chokepoint transits", "ships / day", dayTotals(stats, "ships")),
    counter("fires", "Fire detections", "per day", dayTotals(stats, "fires")),
  ].filter((c): c is HudCounter => c !== null);
  const quakes = events.filter((e) => e.kind === "quake" && e.starts_at && now - Date.parse(e.starts_at) < 86400000).length;
  const outages = events.filter((e) => e.kind === "outage" && e.ends_at === null).length;
  if (events.length > 0) {
    counters.push({ key: "quakes", label: "Quakes", unit: "last 24 h", value: quakes, pct: null, spark: [], href: "/live" });
    counters.push({ key: "outages", label: "Outages", unit: "ongoing", value: outages, pct: null, spark: [], href: "/live" });
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
    url: web(r.source_url), ours: r.source === "corpus", until: untilWords(r.on_date, today),
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
