import { cache } from "react";

import { actorIds } from "./actors";
import { getAllMeta } from "./articles";
import { addDays, calendarItems, todayIso } from "./calendar";
import { fmtDay, latestDaily } from "./daily";
import { dossierList } from "./dossier";
import { latestSnapshot } from "./intel";
import { liveSummary } from "./live";
import { getMenus } from "./radar";
import { recordLedger } from "./record";
import { recentSanctions } from "./sanctions";

// The site's sections as doors: one line saying what is behind each, plus a small live hint read from the
// published data ("12 theaters · 3 escalating"). Home and the Intelligence directory share this, so the two
// never describe a section differently. A hint is "" when its data is missing: a door never shows a zero
// it does not know.

export type Door = { href: string; title: string; line: string; hint: string };

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

const hints = cache(async () => {
  const [daily, theaters, actors, ledger, snap, articles, menus, live, upcoming, sanctions] = await Promise.all([
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
    briefs: snap && snap.briefs.length > 0 ? plural(snap.briefs.length, "brief") : "",
    pulses: pulses.length > 0 ? `${plural(pulses.length, "Pulse")}${severe > 0 ? ` · ${severe} severe or worse` : ""}` : "",
    articles: articles.length > 0 ? `${plural(articles.length, "article")} · latest ${articles[0].date}` : "",
    radar: menus[0] ? plural(menus[0].leads.length, "headline") : "",
    live: live && live.headlines.length > 0 ? `${plural(live.headlines.length, "signal")} now` : "",
    calendar: ahead30.length > 0 ? `${plural(ahead30.length, "date")} · next 30 days` : "",
    sanctions: sanctions.length > 0 ? `${plural(sanctions.filter((s) => s.action === "designated").length, "addition")} · last 30 days` : "",
  };
});

/** Every section of the site as a door, in the order a newcomer should meet them. */
export async function homeDoors(): Promise<Door[]> {
  const h = await hints();
  return [
    { href: "/geopolitics", title: "Geopolitics", line: "Today's report on the world's hot spots, theater by theater.", hint: h.daily },
    { href: "/live", title: "Live map", line: "Ships, aircraft, quakes, fires and outages as they happen.", hint: h.live },
    { href: "/calendar", title: "Calendar", line: "Elections, central-bank decisions and deadlines coming up.", hint: h.calendar },
    { href: "/intel/theaters", title: "Theaters", line: "One living dossier for each conflict and standoff.", hint: h.theaters },
    { href: "/intel/actors", title: "Actors", line: "The states behind the news, side by side.", hint: h.actors },
    { href: "/pulses", title: "Pulses", line: "How tense each relationship is, from calm to critical.", hint: h.pulses },
    { href: "/intel/record", title: "The record", line: "What leaders said, in their own words.", hint: h.record },
    { href: "/articles", title: "Articles", line: "Longer reporting, with the sources shown.", hint: h.articles },
    { href: "/radar", title: "Radar", line: "Headlines as other outlets reported them, not yet verified.", hint: h.radar },
  ];
}

/** The Intelligence section's directory: the depth behind the daily report. */
export async function intelDoors(): Promise<Door[]> {
  const h = await hints();
  return [
    { href: "/intel/situation", title: "Situation room", line: "What changed, and how well we are calling it.", hint: h.pulses },
    { href: "/intel/theaters", title: "Theaters", line: "A dossier for each conflict: where it stands and where it is heading.", hint: h.theaters },
    { href: "/intel/actors", title: "Actors", line: "Population, economy, energy and military of each state.", hint: h.actors },
    { href: "/intel/briefs", title: "Briefs", line: "Researched deep reads of a single theater.", hint: h.briefs },
    { href: "/intel/graph", title: "Relationships", line: "States and theaters as one network: who is involved where.", hint: h.graph },
    { href: "/intel/record", title: "The record", line: "Statements by leaders and institutions, with transcripts.", hint: h.record },
    { href: "/intel/sanctions", title: "Sanctions", line: "Who was added to or removed from the US, UK and EU lists.", hint: h.sanctions },
    { href: "/calendar", title: "Calendar", line: "What is scheduled in the next 30 days, with sources.", hint: h.calendar },
    { href: "/pulses", title: "Pulses", line: "Every relationship on one 0 to 100 scale.", hint: h.pulses },
    { href: "/geopolitics", title: "Daily report", line: "The day, read theater by theater.", hint: h.daily },
  ];
}
