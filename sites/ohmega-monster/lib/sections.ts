import { cache } from "react";

import { actorIds } from "./actors";
import { aiBenchmarks } from "./ai-benchmarks";
import { getAllMeta } from "./articles";
import { addDays, calendarItems, todayIso } from "./calendar";
import { latestZones, recentEvents } from "./conflict";
import { fmtDay, latestDaily } from "./daily";
import { dossierList } from "./dossier";
import { latestSnapshot } from "./intel";
import { liveSummary } from "./live";
import { maritimeEvents } from "./maritime";
import { getMenus } from "./radar";
import { recordLedger } from "./record";
import { recentSanctions } from "./sanctions";
import { satelliteDoc } from "./satellite";
import { trackRecord } from "./track-record";

// The site's sections as doors: one line saying what is behind each, plus a small live hint read from the
// published data ("12 theaters · 3 escalating"). Home and the Intelligence directory share this, so the two
// never describe a section differently. A hint is "" when its data is missing: a door never shows a zero
// it does not know.

export type Door = { href: string; title: string; line: string; hint: string };

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

const hints = cache(async () => {
  const [daily, theaters, actors, ledger, snap, articles, menus, live, upcoming, sanctions, maritime, track, ai, aiDaily, attacks, jam, satellite] = await Promise.all([
    latestDaily("geopolitics"),
    dossierList(),
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
    latestDaily("ai"),
    recentEvents(3, 800),
    latestZones(),
    satelliteDoc(),
  ]);
  const ahead30 = upcoming.filter((r) => r.on_date <= addDays(todayIso(), 30));
  const active = theaters.filter((t) => !t.merged_into);
  const rising = active.filter((t) => t.escalation_direction === "rising").length;
  const pulses = (snap?.situations ?? []).flatMap((s) => s.pulses);
  const severe = pulses.filter((p) => p.band === "severe" || p.band === "critical").length;
  return {
    daily: daily ? `${fmtDay(daily.date)}` : "",
    theaters: active.length > 0 ? `${plural(active.length, "theater")}${rising > 0 ? ` · ${rising} escalating` : ""}` : "",
    actors: actors.length > 0 ? plural(actors.length, "state profile") : "",
    graph: active.length > 0 && actors.length > 0 ? `${plural(actors.length, "state")} · ${plural(active.length, "theater")}` : "",
    record: ledger && ledger.count > 0 ? `${plural(ledger.statements.length, "statement")} · last ${ledger.window_days} days` : "",
    pulses: pulses.length > 0 ? `${plural(pulses.length, "Pulse")}${severe > 0 ? ` · ${severe} severe or worse` : ""}` : "",
    articles: articles.length > 0 ? `${plural(articles.length, "article")} · latest ${articles[0].date}` : "",
    radar: menus[0] ? plural(menus[0].leads.length, "headline") : "",
    live: live && live.headlines.length > 0 ? `${plural(live.headlines.length, "signal")} now` : "",
    calendar: ahead30.length > 0 ? `${plural(ahead30.length, "date")} · next 30 days` : "",
    maritime: maritime.length > 0 ? `${plural(maritime.filter((m) => m.ended_at === null).length, "event")} going · last 30 days` : "",
    track: track ? `${plural(track.scores.compared, "market")} compared · ${plural(track.markets.open, "open market")}` : "",
    ai: ai ? `${plural(ai.benchmarks.length, "benchmark")} · ${plural(ai.labs.length, "lab")}` : "",
    aiDaily: aiDaily ? fmtDay(aiDaily.date) : "",
    attacks: attacks.length > 0 ? `${plural(attacks.length, "event")} · last 3 days` : "",
    gnss: jam && jam.zones.length > 0 ? `${plural(jam.zones.filter((z) => z.source === "ohmega_adsb").length || jam.zones.length, "zone")} · ${fmtDay(jam.day)}` : "",
    satellite: satellite && satellite.counts.with_imagery > 0 ? `${plural(satellite.counts.with_imagery, "place")}${satellite.counts.changed > 0 ? ` · ${satellite.counts.changed} changed` : ""}` : "",
    sanctions: sanctions.length > 0 ? `${plural(sanctions.filter((s) => s.action === "designated").length, "addition")} · last 30 days` : "",
  };
});

/** The site's front doors: the three products first (Daily, Theaters, Articles), then Live and the tools. */
export async function homeDoors(): Promise<Door[]> {
  const h = await hints();
  return [
    { href: "/geopolitics", title: "The Daily", line: "Today's report on the world's hot spots, theater by theater.", hint: h.daily },
    { href: "/intel/theaters", title: "Theaters", line: "One living file for each conflict and standoff, day by day.", hint: h.theaters },
    { href: "/articles", title: "Articles", line: "Longer reporting, with the sources shown.", hint: h.articles },
    { href: "/live", title: "Live map", line: "Ships, aircraft, quakes, fires and outages as they happen.", hint: h.live },
    { href: "/intel", title: "Data & tools", line: "Pulses, the record, calendar, sanctions, maritime, actors and more.", hint: "" },
  ];
}

/** Data & tools: instruments behind the three products. None of these is a publication. */
export async function toolDoors(): Promise<Door[]> {
  const h = await hints();
  return [
    { href: "/pulses", title: "Pulses", line: "Every relationship on one 0 to 100 scale.", hint: h.pulses },
    { href: "/intel/record", title: "The record", line: "Statements by leaders and institutions, with transcripts.", hint: h.record },
    { href: "/calendar", title: "Calendar", line: "What is scheduled in the next 30 days, with sources.", hint: h.calendar },
    { href: "/intel/sanctions", title: "Sanctions", line: "Who was added to or removed from the US, UK and EU lists.", hint: h.sanctions },
    { href: "/intel/attacks", title: "Attack log", line: "Attacks, clashes and mass-violence events reported by GDELT, ACLED and others, with the source and its limits.", hint: h.attacks },
    { href: "/intel/gnss", title: "GPS interference", line: "Where aircraft report poor navigation accuracy: signs of GPS jamming, cross-checked against GPSJam.", hint: h.gnss },
    { href: "/intel/maritime", title: "Maritime", line: "Ships that went dark, met at sea, changed identity or matched a sanctions list.", hint: h.maritime },
    { href: "/intel/satellite", title: "Satellite", line: "Fresh imagery of struck and watched places, before and after, with change flagged as a machine signal.", hint: h.satellite },
    { href: "/intel/forecasts", title: "Forecasts", line: "Every open forecast on one timeline, and the track record.", hint: "" },
    { href: "/intel/track-record", title: "Track record", line: "Our forecasts scored against Polymarket prices, misses included. Paper only.", hint: h.track },
    { href: "/ai", title: "AI Daily", line: "The Daily for artificial intelligence: the labs' race, chips, policy, security, open weights and capital.", hint: h.aiDaily },
    { href: "/intel/ai", title: "AI benchmarks", line: "Frontier model scores on public benchmarks, open against closed, lab by lab.", hint: h.ai },
    { href: "/intel/graph", title: "Graph", line: "States and theaters as one network: who is involved where.", hint: h.graph },
    { href: "/live", title: "Live", line: "The live map: ships, aircraft, quakes, fires and outages.", hint: h.live },
    { href: "/intel/actors", title: "Actors", line: "Population, economy, energy and military of each state.", hint: h.actors },
    { href: "/headlines", title: "Headlines", line: "Other outlets' headlines, not verified by us.", hint: h.radar },
  ];
}
