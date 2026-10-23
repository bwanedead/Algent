import { cache } from "react";

import { aiBenchmarks } from "./ai-benchmarks";
import { getAllMeta } from "./articles";
import { CADENCE_HOURS, newest } from "./fresh";
import { liveSummary } from "./live";
import { maritimeCounts, maritimeLive } from "./maritime";
import { getMenus } from "./radar";
import { satelliteDoc } from "./satellite";
import { productStatuses, withStatus } from "./status";
import { statDef } from "./stats/registry";
import { shortDate, statView } from "./stats/render";
import { trackRecord } from "./track-record";
import { homeView } from "./views";

// The site's sections as doors: one line saying what is behind each, a small live hint read from the published data
// ("12 active situations · 3 escalating"), and the product's as-of stamp so every row can say how old it is and whether that is late for
// its own cadence (components/Doors.tsx renders both). Home and the Data hub share this, so the two never describe a section
// differently. A hint is "" when its data is missing: a door never shows a zero it does not know. The map of what exists is
// docs/architecture/information-architecture.md; a new product is placed there before it gets a door here.
// The counts that need many documents (active situations, state profiles, statements on file, Pulses, calendar, sanctions) come from the home view's
// `facts` (backend views/home.py); the rest are single small documents read here.

export type Door = {
  href: string;
  title: string;
  line: string;
  hint: string;
  /** When the product was last refreshed (ISO time or bare day); "" when it has no cheap stamp. */
  stamp?: string;
  /** When the product was last verified alive (its status file, lib/status.ts); staleness is judged on this when present, `stamp` is then "what's new". */
  checked?: string;
  /** How often the product is meant to refresh, in hours (lib/fresh.ts CADENCE_HOURS); staleness is judged against it. */
  cadenceHours?: number;
};

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

const hints = cache(async () => {
  const [home, articles, menus, live, maritime, maritimeNewest, track, ai, satellite, st] = await Promise.all([
    homeView(),
    getAllMeta(),
    getMenus(),
    liveSummary(),
    maritimeCounts(),
    maritimeLive(300),
    trackRecord(),
    aiBenchmarks(),
    satelliteDoc(),
    productStatuses(["sanctions", "calendar", "ai_benchmarks", "markets", "maritime", "menu"]),
  ]);
  const f = home?.facts;
  // One universe for every situation count: the active ones (not quiet, not merged, not a one-day Spotlight), across all desks.
  const active = f?.situations.active ?? 0;
  const rising = f?.situations.rising ?? 0;
  const actors = f?.actors ?? 0;
  const pulses = f?.pulses.total ?? 0;
  const severe = f?.pulses.severe ?? 0;
  const ledger = f?.record ?? null;
  const calendar30 = f?.calendar_30d ?? 0;
  const additions = f?.sanctions.additions ?? 0;
  return {
    daily: { hint: "", stamp: f?.daily_stamp ?? "" },
    situations: {
      hint: active > 0 ? `${plural(active, "active situation")}${rising > 0 ? ` · ${rising} escalating` : ""}` : "",
      stamp: f?.situations.stamp ?? "",
    },
    actors: actors > 0 ? plural(actors, "state profile") : "",
    graph: active > 0 && actors > 0 ? `${plural(actors, "state")} · ${plural(active, "active situation")}` : "",
    // The export is capped: the hint shows the window's real total when the document carries it, else "latest N".
    record: ledger && ledger.count > 0
      ? `${statView({ id: "door_statements", value: ledger.shown, cap: { limit: 1500, total: ledger.total } }).text} statements · last ${ledger.window_days} days`
      : "",
    recordStamp: ledger?.as_of ?? "",
    pulses: pulses > 0 ? `${plural(pulses, "Pulse")}${severe > 0 ? ` · ${severe} severe or worse` : ""} · model-assessed` : "",
    pulsesStamp: f?.pulses.built_at ?? "",
    articles: { hint: articles.length > 0 ? `${plural(articles.length, "article")}` : "", stamp: articles[0]?.published_at || articles[0]?.date || "" },
    headlines: { hint: menus[0] ? plural(menus[0].leads.length, "headline") : "", ...withStatus(menus[0]?.builtAt ?? "", st.menu) },
    live: { hint: live && live.headlines.length > 0 ? `${plural(live.headlines.length, "signal")} now` : "", stamp: live?.as_of ?? "" },
    satellite: satellite && satellite.counts.with_imagery > 0 ? `${plural(satellite.counts.with_imagery, "place")}${satellite.counts.changed > 0 ? ` · ${satellite.counts.changed} changed` : ""}` : "",
    calendar: calendar30 > 0 ? `${plural(calendar30, "date")} · next 30 days` : "",
    calendarStatus: withStatus("", st.calendar),
    maritime: {
      // A real count (a list fetch is capped at 1000 rows), over the detectors' own history rather than a "last 30 days" they have not run for.
      hint: maritime && maritime.total > 0 ? `${plural(maritime.total, "event")} · since ${shortDate(statDef("maritime_events").baseline_since ?? "")}` : "",
      ...withStatus(newest(maritimeNewest.map((m) => m.updated_at)), st.maritime),
    },
    track: { hint: track ? `${plural(track.scores.compared, "market")} compared · ${plural(track.markets.open, "open market")}` : "", ...withStatus(track?.as_of ?? "", st.markets) },
    ai: { hint: ai ? `${plural(ai.benchmarks.length, "benchmark")} · ${plural(ai.labs.length, "lab")}` : "", ...withStatus(ai?.as_of ?? "", st.ai_benchmarks) },
    sanctions: {
      hint: additions > 0 ? `${plural(additions, "addition")} · since ${shortDate(statDef("sanctions_changes").baseline_since ?? "")}` : "",
      ...withStatus(f?.sanctions.newest_observed ?? "", st.sanctions),
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
    { href: "/intel/track-record", title: "Prediction bots", line: "Our forecasts and paper trades against Polymarket: every bet, the running P&L, misses included.", hint: h.track.hint, stamp: h.track.stamp, checked: h.track.checked, cadenceHours: CADENCE_HOURS.track },
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
        { href: "/intel/maritime", title: "Maritime", line: "Ships that went dark, met at sea, changed identity or matched a sanctions list.", hint: h.maritime.hint, stamp: h.maritime.stamp, checked: h.maritime.checked, cadenceHours: CADENCE_HOURS.maritime },
        { href: "/intel/sanctions", title: "Sanctions", line: "Who was added to or removed from the US, UK and EU lists.", hint: h.sanctions.hint, stamp: h.sanctions.stamp, checked: h.sanctions.checked, cadenceHours: CADENCE_HOURS.sanctions },
        { href: "/intel/satellite", title: "Satellite", line: "Fresh imagery of struck and watched places, before and after, with change flagged as a machine signal.", hint: h.satellite },
        { href: "/calendar", title: "Calendar", line: "What is scheduled in the next 30 days, with sources.", hint: h.calendar, ...h.calendarStatus, cadenceHours: CADENCE_HOURS.calendar },
        { href: "/intel/ai", title: "AI benchmarks", line: "Frontier model scores on public benchmarks, open against closed, lab by lab.", hint: h.ai.hint, stamp: h.ai.stamp, checked: h.ai.checked, cadenceHours: CADENCE_HOURS.benchmarks },
        { href: "/intel/actors", title: "Countries", line: "Population, economy, energy and military of each state.", hint: h.actors },
        { href: "/intel/record", title: "The record", line: "Statements by leaders and institutions, with transcripts.", hint: h.record, stamp: h.recordStamp, cadenceHours: CADENCE_HOURS.statements },
        { href: "/intel/graph", title: "Graph", line: "States and situations as one network: who is involved where.", hint: h.graph },
        { href: "/daily/headlines", title: "Headlines", line: "Other outlets' headlines, not verified by us.", hint: h.headlines.hint, stamp: h.headlines.stamp, checked: h.headlines.checked, cadenceHours: CADENCE_HOURS.headlines },
      ],
    },
    {
      id: "judgments",
      title: "Judgments",
      lead: "What we think will happen, kept on the record and scored. Our reading, not a measurement.",
      doors: [
        { href: "/pulses", title: "Pulses", line: "Every relationship on one 0 to 100 scale.", hint: h.pulses, stamp: h.pulsesStamp, cadenceHours: CADENCE_HOURS.pulses },
        { href: "/intel/forecasts", title: "Forecasts", line: "Every open forecast, and how our calls scored against Polymarket prices, misses included. Paper only.", hint: h.track.hint, stamp: h.track.stamp, checked: h.track.checked, cadenceHours: CADENCE_HOURS.track },
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
