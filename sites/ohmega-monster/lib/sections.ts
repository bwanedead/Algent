import { cache } from "react";

import { actorIds } from "./actors";
import { aiBenchmarks } from "./ai-benchmarks";
import { getAllMeta } from "./articles";
import { addDays, calendarItems, todayIso } from "./calendar";
import { latestDaily } from "./daily";
import { DESKS } from "./desks";
import { CADENCE_HOURS, newest } from "./fresh";
import { latestSnapshot } from "./intel";
import { liveSummary } from "./live";
import { maritimeEvents } from "./maritime";
import { getMenus } from "./radar";
import { recordLedger } from "./record";
import { recentSanctions } from "./sanctions";
import { situationsByDesk } from "./situations";
import { trackRecord } from "./track-record";

// The site's sections as doors: one line saying what is behind each, a small live hint read from the published data
// ("12 active situations · 3 escalating"), and the product's as-of stamp so every row can say how old it is and whether that is late for
// its own cadence (components/Doors.tsx renders both). Home and the Data hub share this, so the two never describe a section
// differently. A hint is "" when its data is missing: a door never shows a zero it does not know. The map of what exists is
// docs/architecture/information-architecture.md; a new product is placed there before it gets a door here.

export type Door = {
  href: string;
  title: string;
  line: string;
  hint: string;
  /** When the product was last refreshed (ISO time or bare day); "" when it has no cheap stamp. */
  stamp?: string;
  /** How often the product is meant to refresh, in hours (lib/fresh.ts CADENCE_HOURS); staleness is judged against it. */
  cadenceHours?: number;
};

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

const hints = cache(async () => {
  const [dailies, situations, actors, ledger, snap, articles, menus, live, upcoming, sanctions, maritime, track, ai] = await Promise.all([
    Promise.all(DESKS.map((d) => latestDaily(d.id))),
    situationsByDesk(),
    actorIds(),
    recordLedger(),
    latestSnapshot(),
    getAllMeta(),
    getMenus(),
    liveSummary(),
    calendarItems(30),
    recentSanctions(30),
    maritimeEvents(300),
    trackRecord(),
    aiBenchmarks(),
  ]);
  const ahead30 = upcoming.filter((r) => r.on_date <= addDays(todayIso(), 30));
  // One universe for every situation count: the active ones (not quiet, not merged, not a one-day Spotlight), across all desks.
  const active = situations.flatMap((g) => g.active);
  const rising = active.filter((r) => r.item.escalation_direction === "rising").length;
  const pulses = (snap?.situations ?? []).flatMap((s) => s.pulses);
  const severe = pulses.filter((p) => p.band === "severe" || p.band === "critical").length;
  const reports = dailies.filter((r): r is NonNullable<typeof r> => r !== null);
  return {
    daily: { hint: "", stamp: newest(reports.map((r) => r.built_at || r.date)) },
    situations: {
      hint: active.length > 0 ? `${plural(active.length, "active situation")}${rising > 0 ? ` · ${rising} escalating` : ""}` : "",
      stamp: newest(active.map((r) => r.item.last_seen)),
    },
    actors: actors.length > 0 ? plural(actors.length, "state profile") : "",
    graph: active.length > 0 && actors.length > 0 ? `${plural(actors.length, "state")} · ${plural(active.length, "active situation")}` : "",
    record: ledger && ledger.count > 0 ? `${plural(ledger.statements.length, "statement")} · last ${ledger.window_days} days` : "",
    recordStamp: ledger?.as_of ?? "",
    pulses: pulses.length > 0 ? `${plural(pulses.length, "Pulse")}${severe > 0 ? ` · ${severe} severe or worse` : ""}` : "",
    pulsesStamp: snap?.built_at ?? "",
    articles: { hint: articles.length > 0 ? `${plural(articles.length, "article")}` : "", stamp: articles[0]?.published_at || articles[0]?.date || "" },
    headlines: { hint: menus[0] ? plural(menus[0].leads.length, "headline") : "", stamp: menus[0]?.builtAt ?? "" },
    live: { hint: live && live.headlines.length > 0 ? `${plural(live.headlines.length, "signal")} now` : "", stamp: live?.as_of ?? "" },
    calendar: ahead30.length > 0 ? `${plural(ahead30.length, "date")} · next 30 days` : "",
    maritime: {
      hint: maritime.length > 0 ? `${plural(maritime.filter((m) => m.ended_at === null).length, "event")} going · last 30 days` : "",
      stamp: newest(maritime.map((m) => m.updated_at)),
    },
    track: { hint: track ? `${plural(track.scores.compared, "market")} compared · ${plural(track.markets.open, "open market")}` : "", stamp: track?.as_of ?? "" },
    ai: { hint: ai ? `${plural(ai.benchmarks.length, "benchmark")} · ${plural(ai.labs.length, "lab")}` : "", stamp: ai?.as_of ?? "" },
    sanctions: {
      hint: sanctions.length > 0 ? `${plural(sanctions.filter((s) => s.action === "designated").length, "addition")} · last 30 days` : "",
      stamp: newest(sanctions.map((s) => s.observed_on)),
    },
  };
});

/** The site's front doors on Home: the three publications first (Daily, Situations, Articles), then the globe, the live map and Data. */
export async function homeDoors(): Promise<Door[]> {
  const h = await hints();
  return [
    { href: "/daily", title: "The Daily", line: "One report per desk per day: geopolitics and AI.", hint: h.daily.hint, stamp: h.daily.stamp, cadenceHours: CADENCE_HOURS.daily },
    { href: "/situations", title: "Situations", line: "Each long-running story as one living file, day by day.", hint: h.situations.hint, stamp: h.situations.stamp, cadenceHours: CADENCE_HOURS.situation },
    { href: "/articles", title: "Articles", line: "Longer reporting, with the sources shown.", hint: h.articles.hint, stamp: h.articles.stamp, cadenceHours: CADENCE_HOURS.article },
    { href: "/globe", title: "Globe", line: "The world on a globe: flows, countries and situations to pin.", hint: "" },
    { href: "/live", title: "Live map", line: "Ships, aircraft, quakes, fires and outages as they happen.", hint: h.live.hint, stamp: h.live.stamp, cadenceHours: CADENCE_HOURS.live },
    { href: "/data", title: "Data", line: "Measured layers, scored judgments and feeds for machines.", hint: "" },
  ];
}

export type DataGroup = { id: "measured" | "judgments" | "machines"; title: string; lead: string; doors: Door[] };

/** The Data hub (docs/architecture/information-architecture.md §3): Measured (no editorial voice), Judgments (what we think, kept and scored), For machines. */
export async function dataGroups(): Promise<DataGroup[]> {
  const h = await hints();
  return [
    {
      id: "measured",
      title: "Measured",
      lead: "Collected from public sources, no editorial voice.",
      doors: [
        { href: "/live", title: "Live map", line: "Ships, aircraft, quakes, fires and outages as they happen.", hint: h.live.hint, stamp: h.live.stamp, cadenceHours: CADENCE_HOURS.live },
        { href: "/intel/maritime", title: "Maritime", line: "Ships that went dark, met at sea, changed identity or matched a sanctions list.", hint: h.maritime.hint, stamp: h.maritime.stamp, cadenceHours: CADENCE_HOURS.maritime },
        { href: "/intel/sanctions", title: "Sanctions", line: "Who was added to or removed from the US, UK and EU lists.", hint: h.sanctions.hint, stamp: h.sanctions.stamp, cadenceHours: CADENCE_HOURS.sanctions },
        { href: "/calendar", title: "Calendar", line: "What is scheduled in the next 30 days, with sources.", hint: h.calendar },
        { href: "/intel/ai", title: "AI benchmarks", line: "Frontier model scores on public benchmarks, open against closed, lab by lab.", hint: h.ai.hint, stamp: h.ai.stamp, cadenceHours: CADENCE_HOURS.benchmarks },
        { href: "/intel/actors", title: "Countries", line: "Population, economy, energy and military of each state.", hint: h.actors },
        { href: "/intel/record", title: "The record", line: "Statements by leaders and institutions, with transcripts.", hint: h.record, stamp: h.recordStamp, cadenceHours: CADENCE_HOURS.statements },
        { href: "/intel/graph", title: "Graph", line: "States and situations as one network: who is involved where.", hint: h.graph },
        { href: "/daily/headlines", title: "Headlines", line: "Other outlets' headlines, not verified by us.", hint: h.headlines.hint, stamp: h.headlines.stamp, cadenceHours: CADENCE_HOURS.headlines },
      ],
    },
    {
      id: "judgments",
      title: "Judgments",
      lead: "What we think will happen, kept on the record and scored. Our reading, not a measurement.",
      doors: [
        { href: "/pulses", title: "Pulses", line: "Every relationship on one 0 to 100 scale.", hint: h.pulses, stamp: h.pulsesStamp, cadenceHours: CADENCE_HOURS.pulses },
        { href: "/intel/forecasts", title: "Forecasts", line: "Every open forecast, and how our calls scored against Polymarket prices, misses included. Paper only.", hint: h.track.hint, stamp: h.track.stamp, cadenceHours: CADENCE_HOURS.track },
      ],
    },
    {
      id: "machines",
      title: "For machines",
      lead: "The same documents the pages read, as an API, an MCP server and feeds.",
      doors: [
        { href: "/developers", title: "API and MCP", line: "A read-only JSON API and a remote MCP server over the reports, Pulses, statements and measured series.", hint: "" },
        { href: "/feed.xml", title: "RSS", line: "New articles as they publish.", hint: "" },
        { href: "/llms.txt", title: "llms.txt", line: "A plain-text guide to the site's shape and feeds, for agents.", hint: "" },
      ],
    },
  ];
}
