// The contract between the worker server's views and the site's readers, checked end to end with no network and no build:
//
//   node scripts/view-check.mjs <views.json>
//
// <views.json> is {"<view key>": <view body>} as the backend builds it (backend/tests/test_site_views_contract.py writes one from its fixture record and runs this
// script; it needs `npm install` once for the `typescript` package, or TYPESCRIPT_PATH). The site's own lib code runs unchanged against those views through a fake
// bucket: the globe panel and HUD, the situations pages, the actor context, the development and place pages, Home, and the agent tools (entity, about, timeline,
// related, series, search) with their provenance and basis, plus the rate-limit seam. Exits 1 on the first failed expectation.
//
// The expectations name the backend fixture's entities (Iran, IRGC, the Hormuz theater): this is a contract test of that record, not a smoke test of live data.

import assert from "node:assert/strict";
import fs from "node:fs";
import { register } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import zlib from "node:zlib";

const here = path.dirname(fileURLToPath(import.meta.url));
const views = JSON.parse(fs.readFileSync(path.resolve(process.argv[2] ?? "views.json"), "utf8"));
process.env.NEXT_PUBLIC_DATA_BASE = "http://views.local";
register("./ts-hooks.mjs", pathToFileURL(`${here}/`));

globalThis.fetch = async (url) => {
  const m = /^http:\/\/views\.local\/docs\/views\/(.+)\.json\.gz$/.exec(String(url));
  return m && views[m[1]] ? new Response(zlib.gzipSync(Buffer.from(JSON.stringify(views[m[1]]))), { status: 200 }) : new Response("", { status: 404 });
};

const lib = (f) => import(pathToFileURL(path.resolve(here, "..", "lib", f)).href);
const checks = [];
const check = (name, fn) => checks.push([name, fn]);

check("the globe panel: raw stats worded, counts, grid, briefs cut to a line", async () => {
  const { countryPanel } = await lib("globe-country.ts");
  const p = await countryPanel("IR");
  const gdp = p.stats.find((s) => s.id === "gdp");
  assert.equal(gdp.text, "$400B");
  assert.ok(gdp.median && gdp.pos >= 0 && gdp.pos <= 1);
  assert.equal(p.counts.sanctions, 1);
  assert.equal(p.grid.line, "Grid down 12% in 30 days.");
  assert.ok(p.briefs.length > 0 && p.briefs.every((b) => b.text.length <= 200 && b.href.startsWith("/daily/geopolitics")));
  assert.deepEqual((await countryPanel("TV")).stats, []); // nothing on record: an honest empty panel
  assert.equal(await countryPanel("xx"), null);
});

check("the globe and HUD: channel rows, today's lines, calendar and sanctions worded for the viewer", async () => {
  const { globeData } = await lib("globe-data.ts");
  const { hudData } = await lib("globe-hud.ts");
  const g = await globeData();
  assert.equal(g.countries.IR.name, "Iran");
  assert.equal(g.countries.IR.th, "energy");
  assert.equal(g.countries.IR.theaters[0].href, "/situations/thr_hormuz");
  const h = await hudData();
  assert.equal(h.daily.items[0].kind, "section");
  assert.equal(h.coming[0].label, "Summit or talks");
  assert.match(h.coming[0].until, /^in \d+ days$|^today$|^tomorrow$/);
  assert.equal(h.sanctions[0].type, "Vessel");
  assert.equal(h.trader.equity, 1010);
  assert.ok(h.pulses.length >= 1);
});

check("situations: the index by desk and a stream split into full days and rows", async () => {
  const { situationsByDesk, streamOf } = await lib("situations.ts");
  const { situationView } = await lib("views.ts");
  const groups = await situationsByDesk();
  const geo = groups.find((x) => x.desk.id === "geopolitics");
  assert.deepEqual(geo.active.map((r) => r.item.theater_id), ["thr_hormuz"]);
  assert.deepEqual(geo.quiet.map((r) => r.item.theater_id), ["thr_taiwan"]);
  assert.equal(geo.active[0].dossier.coverage_series.length, 21);
  const stream = streamOf(await situationView("thr_hormuz"));
  assert.equal(stream.total, 2);
  assert.equal(stream.days.length, 2);
  assert.equal(stream.days[0].t.name, "Hormuz crisis");
  assert.equal(stream.days[0].events, true);
  assert.deepEqual(streamOf(null), { total: 0, days: [], earlier: [], earlierTotal: 0 });
});

check("the entity graph and an actor's context", async () => {
  const { actorContext, entityGraph, entityIndex, textLinker } = await lib("entities.ts");
  const idx = await entityIndex();
  assert.ok(idx.refs.get("thr_hormuz").linked && idx.ties.get("thr_hormuz").get("IR") > 0 && idx.linkable.has("IR"));
  assert.ok((await entityGraph()).links.length > 0);
  assert.ok(await textLinker());
  const ctx = await actorContext("IR");
  assert.equal(ctx.name, "Iran");
  assert.deepEqual(ctx.theaters.map((t) => t.id), ["thr_hormuz"]);
  assert.equal(ctx.said.length, 2);
  assert.match(ctx.developments[0].event, /^\/intel\/events\/2026-10-23\/thr_hormuz\/\d+$/);
  assert.equal(await actorContext("TV"), null);
});

check("the development page and the place page", async () => {
  const { eventView } = await lib("views.ts");
  const { parseDevelopment } = await lib("daily.ts");
  const { placeContext } = await lib("places.ts");
  const ev = await eventView("2026-10-23", "thr_hormuz");
  assert.equal(parseDevelopment(ev.developments[0]).headline, "Hormuz crisis development 1");
  assert.deepEqual(ev.actor_isos[0], ["IR", "US"]);
  const place = await placeContext("plant1");
  assert.equal(place.asset.name, "Bandar Abbas power plant");
  assert.equal(place.history[0].status, "reported_damaged");
  assert.equal(place.theaters[0].id, "thr_hormuz");
  assert.equal(await placeContext("nope"), null);
});

check("home, the daily hub and the doors", async () => {
  const { homeView, dailyHubView } = await lib("views.ts");
  const { dailyFromView } = await lib("daily.ts");
  const home = await homeView();
  const report = dailyFromView(home.reports.geopolitics, "geopolitics");
  assert.equal(report.headline, "Hormuz stays shut");
  assert.equal(report.date, "2026-10-23");
  assert.ok(report.theaters.some((t) => t.numbers?.trackers.length === 1));
  assert.deepEqual(home.moving.map((m) => m.id), ["thr_hormuz", "thr_chips"]);
  const hub = await dailyHubView();
  assert.equal(hub.desks.find((d) => d.desk === "geopolitics").dates_total, 2);
  const { homeDoors } = await lib("sections.ts");
  assert.match((await homeDoors())[1].hint, /^2 active situations · 2 escalating$/);
});

check("agent tools: entity, about, timeline, related, series, search - with provenance and basis", async () => {
  const ops = await lib("api/ops-corpus.ts");
  const { searchOp } = await lib("api/ops-content.ts");
  const { dispatch } = await lib("api/router.ts");
  const { respond } = await lib("api/envelope.ts");
  const { TOOLS, runTool } = await lib("api/mcp-tools.ts");

  const e = await ops.entityOp({ name: "Revolutionary Guards" }); // an alias
  assert.equal(e.data.match.key, "entity/org/irgc");
  assert.equal(e.source, "ohmega.view.entity/1");
  assert.equal(e.provenance.sources[0].product, "corpus_index");
  assert.equal((await ops.entityOp({ name: "iran" })).data.match.key, "country/IR"); // a country wins
  assert.equal((await ops.entityOp({ name: "Hormuz crisis" })).data.entity.kind, "situation");

  const about = await ops.aboutOp({ entity: "IRGC", since: "2026-10-01", kinds: "claim" });
  assert.equal(about.data.claims.length, 1);
  assert.equal(about.data.claims[0].sources[0], "https://reuters.com/hormuz");
  assert.equal(about.data.claims[0].product, "profiles");
  assert.equal(about.data.documents.length + about.data.events.length, 0);
  const older = await ops.aboutOp({ entity: "IRGC", since: "2026-01-01" });
  assert.match(older.note, /Nothing older than/);

  const tl = await ops.timelineOp({ entity: "IRGC" });
  assert.ok(tl.data.timeline.length >= 2 && tl.data.timeline.every((x, i, a) => i === 0 || a[i - 1].date <= x.date));
  const rel = await ops.relatedOp({ entity: "IRGC", kinds: "person" });
  assert.deepEqual(rel.data.related.map((r) => r.entity), ["person:iran-leader"]);

  const gdp = await ops.seriesOp({ metric: "gdp" });
  assert.equal(gdp.data.basis, "official");
  assert.deepEqual(gdp.basis, ["official"]);
  assert.equal(gdp.data.entities.find((x) => x.entity === "country:IR").latest.value, 4e11);
  const own = await ops.seriesOp({ entity: "Iran", metric: "gdp", since: "2024" });
  assert.deepEqual(own.data.series[0].points, [["2024", 4e11]]);
  assert.ok((await ops.seriesOp({ metric: "gd" })).data.candidates.some((c) => c.metric === "gdp"));

  const hits = await searchOp({ q: "irgc", type: "entity" });
  assert.equal(hits.data.results[0].id, "entity/org/irgc");
  assert.ok((await searchOp({ q: "hormuz closure", type: "document" })).data.results.length > 0);

  const body = await respond(new Request("https://x.test/api/v1/about"), await dispatch(["about"], new URLSearchParams("entity=IRGC&kinds=claim"))).json();
  assert.ok(body.meta.provenance && body.meta.version === "v1" && body.meta.cite_as);
  const text = await runTool(TOOLS.find((t) => t.name === "series"), { metric: "gdp" });
  assert.deepEqual(JSON.parse(text).basis, ["official"]);

  for (const [args, status] of [[{ entity: "zzzqq nothing" }, 404], [{ entity: "x" }, 400], [{ key: "bogus" }, 400]]) {
    await assert.rejects(ops.entityOp(args), (err) => err.status === status);
  }
});

check("the rate-limit seam: a burst, a refusal with Retry-After, a refill, separate surfaces", async () => {
  const rl = await lib("api/ratelimit.ts");
  rl.reset();
  const v1 = rl.surfaceOf("/api/v1/about");
  assert.equal(v1.prefix, "/api/v1");
  assert.equal(rl.surfaceOf("/api/mcp").prefix, "/api/mcp");
  assert.equal(rl.surfaceOf("/api/globe/country/FR"), null); // the site's own endpoints are not limited
  assert.equal(rl.surfaceOf("/api/v10"), null);
  const t0 = 1_000_000;
  for (let i = 0; i < v1.burst; i++) assert.ok(rl.take(v1, "1.2.3.4", t0).allowed, `request ${i + 1} of the burst`);
  const refused = rl.take(v1, "1.2.3.4", t0);
  assert.ok(!refused.allowed && refused.retryAfterSeconds >= 1 && refused.remaining === 0);
  assert.ok(rl.take(v1, "9.9.9.9", t0).allowed); // another client has its own bucket
  assert.ok(rl.take(rl.surfaceOf("/api/mcp"), "1.2.3.4", t0).allowed); // and another surface its own
  assert.ok(rl.take(v1, "1.2.3.4", t0 + refused.retryAfterSeconds * 1000).allowed); // it refills at the sustained rate
  assert.equal(rl.clientOf(new Headers({ "x-forwarded-for": "5.6.7.8, 10.0.0.1" })), "5.6.7.8");
  assert.equal(rl.clientOf(new Headers()), "unknown");
});

let failed = 0;
for (const [name, fn] of checks) {
  try {
    await fn();
    console.log(`ok   ${name}`);
  } catch (e) {
    failed++;
    console.log(`FAIL ${name}\n     ${String(e?.stack ?? e).split("\n").slice(0, 6).join("\n     ")}`);
  }
}
process.exit(failed ? 1 : 0);
