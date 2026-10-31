// The contract between the server's published documents and the site's parsers, checked end to end with no network and no build:
//
//   node scripts/contract-check.mjs <docs.json>
//
// <docs.json> is {"<document path>": <document>}: one typed example per schema (backend `contracts/examples.py`, written by tests/test_site_contracts.py, which runs
// this script; it needs the `typescript` package, or TYPESCRIPT_PATH). The documents are served from a fake bucket and read with the site's OWN readers
// (daily, dossier, actors, sanctions, calendar, maritime, geoledger, track record, live snapshots ...), so a field renamed on either side fails here; and the
// version gate (lib/contract.ts) is exercised: an unknown major or a foreign schema is refused without a crash, an unstamped document is a legacy v1, and the
// reader says "update pending" instead of rendering it. Exits 1 on the first failed expectation.

import assert from "node:assert/strict";
import fs from "node:fs";
import { register } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import zlib from "node:zlib";

const here = path.dirname(fileURLToPath(import.meta.url));
const docs = JSON.parse(fs.readFileSync(path.resolve(process.argv[2] ?? "docs.json"), "utf8"));
process.env.NEXT_PUBLIC_DATA_BASE = "http://contracts.local";
register("./ts-hooks.mjs", pathToFileURL(`${here}/`));

// the same example also serves where the site asks for a sibling path (a vessel's file, the live list)
docs["maritime/live.json"] = docs["maritime/recent.json"];
docs["maritime/vessel/9876543.json"] = docs["maritime/recent.json"];

const normal = (p) => p.replace(/^\/+/, "");
const names = (dir) => Object.keys(docs).filter((p) => p.startsWith(`${dir}/`) && !p.slice(dir.length + 1).includes("/")).map((p) => p.slice(dir.length + 1)).sort();
globalThis.fetch = async (url) => {
  const u = String(url);
  let m = /^http:\/\/contracts\.local\/docs\/(.+)\.gz$/.exec(u);
  if (m) {
    const nm = /^_names\/(.+)\.json$/.exec(m[1]);
    const body = nm ? names(nm[1]) : docs[m[1]];
    return body ? new Response(zlib.gzipSync(Buffer.from(JSON.stringify(body))), { status: 200 }) : new Response("", { status: 404 });
  }
  m = /^http:\/\/contracts\.local\/(live\/.+\.json)(\.gz)?$/.exec(u);
  if (m && docs[m[1]]) {
    const raw = Buffer.from(JSON.stringify(docs[m[1]]));
    return new Response(m[2] ? zlib.gzipSync(raw) : raw, { status: 200 });
  }
  return new Response("", { status: 404 });
};

const lib = (f) => import(pathToFileURL(path.resolve(here, "..", "lib", f)).href);
const checks = [];
const check = (name, fn) => checks.push([name, fn]);
const clone = (x) => JSON.parse(JSON.stringify(x));

check("every example document passes the version gate and carries the stamp its path's contract declares", async () => {
  const { checkDoc, contractFor, parseStamp } = await lib("contract.ts");
  const { publishedDoc } = await lib("store.ts");
  let n = 0;
  for (const [p, doc] of Object.entries(docs)) {
    const row = contractFor(p);
    assert.ok(row, `no contract for ${p}`);
    assert.deepEqual(parseStamp(doc.schema), { id: row.schema, major: row.version }, `${p} is stamped ${doc.schema}`);
    assert.ok(checkDoc(p, doc).ok, p);
    assert.ok(await publishedDoc(p), `${p} was refused by the reader`);
    n++;
  }
  assert.ok(n >= 40, `only ${n} examples`);
});

check("the gate: an unknown major, a foreign schema and a garbled stamp are refused; an unstamped document is a legacy v1; a listed older major is read", async () => {
  const { checkDoc, contractFor } = await lib("contract.ts");
  const d = docs["sanctions/recent.json"];
  assert.ok(!checkDoc("sanctions/recent.json", { ...d, schema: "ohmega.sanctions/2" }).ok);
  assert.ok(!checkDoc("sanctions/recent.json", { ...d, schema: "ohmega.calendar/1" }).ok);
  assert.ok(!checkDoc("sanctions/recent.json", { ...d, schema: "sanctions-v1" }).ok);
  assert.deepEqual(checkDoc("sanctions/recent.json", { rows: [] }), { ok: true, major: 1 });
  assert.ok(checkDoc("sanctions/recent.json", []).ok); // an array carries no stamp
  assert.ok(checkDoc("no/contract/here.json", { schema: "whatever/9" }).ok);
  assert.deepEqual(contractFor("data/track-record.json").accepts, [1, 2]);
  assert.ok(checkDoc("data/track-record.json", { schema: "ohmega.track-record/1" }).ok && checkDoc("data/track-record.json", { schema: "ohmega.track-record/2" }).ok);
  assert.ok(!checkDoc("data/track-record.json", { schema: "ohmega.track-record/3" }).ok);
  assert.equal(contractFor("theaters/index.json").schema, "ohmega.dossier.index");
  assert.equal(contractFor("theaters/thr_x.json").schema, "ohmega.dossier");
  assert.equal(contractFor("docs/live/vessels.json.gz").schema, "ohmega.live.vessels");
});

check("a document in a newer major than the site reads degrades to 'not published' with a remembered reason, never a crash", async () => {
  const { recentSanctions } = await lib("sanctions.ts");
  const { updatePending } = await lib("contract.ts");
  const { aiBenchmarks } = await lib("ai-benchmarks.ts");
  const keep = docs["sanctions/recent.json"];
  assert.equal((await recentSanctions(100000)).length, 1);
  assert.deepEqual(updatePending(), []);
  docs["sanctions/recent.json"] = { ...clone(keep), schema: "ohmega.sanctions/9" };
  assert.deepEqual(await recentSanctions(100000), []);
  assert.equal(updatePending().length, 1);
  assert.match(updatePending()[0], /ohmega\.sanctions\/9/);
  assert.ok(await aiBenchmarks(), "other families are unaffected");
  docs["sanctions/recent.json"] = keep;
});

check("daily, dossier, brief, snapshot (with its Pulses), actors and the record", async () => {
  const { daily } = await lib("daily.ts");
  const { dossier, dossierList } = await lib("dossier.ts");
  const { brief, latestSnapshot } = await lib("intel.ts");
  const { actor, actorIndex } = await lib("actors.ts");
  const { recordLedger } = await lib("record.ts");
  const d = await daily("geopolitics", "2026-10-23");
  assert.equal(d.headline, "Hormuz stays shut");
  assert.equal(d.theaters[0].name, "Hormuz crisis");
  assert.equal(d.theaters[0].temperature.heat, 14);
  assert.equal(d.theaters[0].escalation.direction, "rising");
  const t = await dossier("thr_hormuz");
  assert.equal(t.name, "Hormuz crisis");
  assert.equal(t.escalation_history.length, 23);
  assert.equal(t.coverage_series.length, 23);
  assert.equal((await dossierList())[0].theater_id, "thr_hormuz");
  assert.equal((await brief("hormuz-brief")).bottom_line, "Closure persists.");
  const s = await latestSnapshot();
  assert.equal(s.situations[0].pulses[0].id, "pls_hormuz");
  assert.equal(s.situations[0].pulses[0].band, "severe");
  assert.equal((await actor("IR")).involved.theaters[0].id, "thr_hormuz");
  assert.equal((await actorIndex()).actors[0].iso2, "IR");
  assert.equal((await recordLedger()).statements[0].speaker, "A. Official");
});

check("articles, the headline menu and the forecasts / changes / Pulse feeds", async () => {
  const { getSlugs } = await lib("articles.ts");
  const { articleSource, intelDoc } = await lib("store.ts");
  const { getMenus } = await lib("radar.ts");
  assert.deepEqual(await getSlugs(), ["hello"]);
  assert.match((await articleSource("hello")).markdown, /Body\./);
  assert.equal((await getMenus())[0].leads[0].title, "A lead");
  for (const p of ["data/forecasts.json", "data/changes.json", "data/intel.json", "data/pulses.json", "pulses/pls_hormuz.json"]) assert.ok(await intelDoc(p), p);
});

check("sanctions, calendar, maritime, the geoledger, AI benchmarks and the track record", async () => {
  const { recentSanctions } = await lib("sanctions.ts");
  const { calendarItems, norm, filterRows, NO_FILTER, horizon } = await lib("calendar.ts");
  const { maritimeEvents, maritimeCounts, maritimeLive, maritimeForVessel } = await lib("maritime.ts");
  const { getAsset, assetHistory, queryAssets, getGrid, eventsFor } = await lib("geoledger.ts");
  const { aiBenchmarks } = await lib("ai-benchmarks.ts");
  const { trackRecord } = await lib("track-record.ts");
  const rows = await recentSanctions(100000);
  assert.equal(rows[0].name, "MAR AZUL");
  assert.equal(rows[0].asset_id, "plant1");
  assert.equal((await calendarItems(100000))[0].title, "Gulf summit");
  // the additive fields (topic, importance, grade, situations, sources) arrive as written; a row written before them gets defaults from its kind and confidence
  const c0 = (await calendarItems(100000))[0];
  assert.deepEqual([c0.grade, c0.topic, c0.importance, c0.sources[0].source], ["official", "diplomacy", 3, "official"]);
  const old = norm({ id: "x", on_date: "2099-01-01", end_date: null, title: "t", kind: "election", countries: [], theaters: [], source: "elections", source_url: "u", confidence: "medium", provenance: "aggregated", via: "", active: true });
  assert.deepEqual([old.grade, old.topic, old.importance, old.situations.length], ["announced", "elections", 2, 0]);
  assert.equal(filterRows([c0, { ...old, importance: 1 }], NO_FILTER).length, 1); // routine items are hidden unless asked for
  assert.equal(filterRows([c0, { ...old, importance: 1 }], { ...NO_FILTER, routine: true }).length, 2);
  assert.equal(horizon([c0], "2099-01-14").length, 1); // a day away is inside the 72-hour strip
  const ev = (await maritimeEvents())[0];
  assert.equal(ev.kind, "ais_gap");
  assert.equal(ev.area, "Strait of Hormuz");
  assert.equal((await maritimeLive())[0].id, "m1");
  assert.equal((await maritimeForVessel({ imo: "9876543" }))[0].imo, "9876543");
  assert.deepEqual(await maritimeCounts(), { total: 1, ongoing: 1, byKind: { sanctioned: 0, ais_gap: 1, sts: 0, identity: 0, loiter: 0 } });
  assert.equal((await getAsset("plant1")).status, "reported_damaged");
  assert.equal((await assetHistory("plant1"))[0].claimant, "Iran");
  assert.equal((await queryAssets({ country: "IR" }))[0].id, "plant1");
  assert.equal((await queryAssets({ bbox: [55, 26, 57, 28] }))[0].id, "plant1");
  assert.equal((await getGrid("IR")).line, "Grid down 12% in 30 days.");
  assert.equal((await eventsFor(["plant1"], "2026-10-01", "2026-10-31"))[0].id, "e1");
  assert.equal((await aiBenchmarks()).benchmarks[0].id, "swe");
  const tr = await trackRecord();
  assert.equal(tr.markets.open, 1);
  assert.equal(tr.forecasts, 2);
  // The fast book, the evidence section and the horizons (additive fields): parsed, with a position's evidence trail and a withheld group staying withheld.
  assert.equal(tr.fast.horizon_days, 7);
  assert.equal(tr.fast.open_positions[0].trail[0].href, "/intel/actors/IR");
  assert.equal(tr.fast.open_positions[0].evidence, "sufficient");
  assert.equal(tr.evidence.coverage.sufficient, 2);
  assert.equal(tr.evidence.top_gaps[0].topic, "Hormuz insurance rates");
  assert.equal(tr.evidence.accuracy.forecasts[0].shown, false);
  assert.equal(tr.evidence.accuracy.forecasts[0].brier_ours, null);
  assert.equal(tr.horizons.books.fast.positions, 1);
  // The recipe lab (additive): the best recipe parses with its bins, an absent live side stays null.
  assert.equal(tr.lab.best.protocol, "p0b");
  assert.equal(tr.lab.best.bins_raw[0].hit_rate, 0.56);
  assert.equal(tr.lab.live, null);
  // The day book: its positions carry time to resolution, an un-shown horizon group stays withheld, runs and the data wishes parse.
  assert.equal(tr.day.horizon_hours, 48);
  assert.equal(tr.day.open_positions[0].now_at, `${tr.day.since}T12:05`);
  assert.ok(tr.day.last_at.length > 0);
  assert.deepEqual(tr.day.run_hours, [8, 14, 20]);
  assert.equal(tr.day.open_positions[0].hours_left, 6.5);
  assert.equal(tr.day.by_horizon[0].shown, false);
  assert.equal(tr.day.by_horizon[0].hit_rate, null);
  assert.equal(tr.day.runs[0].orders[0].reason, "Already counted.");
  assert.equal(tr.day.wishes[0].source, "parliament feed");
  assert.equal(tr.day.watchlist[0].market_id, "d2");
  assert.equal(tr.trader.open_positions.length, 0);
});

check("live events, stats, anomalies, the world map, the snapshot layers the map polls, flows and satellite", async () => {
  const { liveEvents, liveStats, liveAnomalies, liveWorld, liveSummary, liveEnergy } = await lib("live.ts");
  const { satelliteDoc } = await lib("satellite.ts");
  const { fetchSnapshot } = await lib("live-shared.ts");
  assert.equal((await liveEvents())[0].title, "M5.1 near Bandar Abbas");
  assert.equal((await liveStats())[0].series_id, "ship.hormuz");
  assert.equal((await liveAnomalies())[0].sentence, "Tankers above normal");
  assert.equal((await liveWorld()).width, 360);
  assert.equal((await liveSummary()).headlines[0].id, "h1");
  assert.equal((await liveEnergy()).tiles[0].id, "brent");
  assert.equal((await satelliteDoc()).sites[0].id, "plant1");
  for (const [name, key, want] of [["fires", "detections", 3], ["vessels", "n", 1], ["aircraft", "n", 1], ["coverage", "deg", 1], ["points", "deg", 0.05], ["tiles/index", "deg", 5], ["tiles/r1c1", "tile", "r1c1"], ["tracks/0", "as_of", docs["live/tracks/0.json"].as_of], ["flows", "today", "2026-10-23"]]) {
    const doc = await fetchSnapshot(name);
    assert.ok(doc, name);
    assert.equal(doc[key], want, `${name}.${key}`);
  }
  docs["live/vessels.json"] = { ...clone(docs["live/vessels.json"]), schema: "ohmega.live.vessels/2" };
  assert.equal(await fetchSnapshot("vessels"), null, "a newer snapshot major is not drawn");
});

check("the status file: checked_at and last_changed_at", async () => {
  const { productStatus, withStatus } = await lib("status.ts");
  const st = await productStatus("sanctions");
  assert.equal(st.checked_at, docs["status/sanctions.json"].checked_at);
  assert.equal(st.last_changed_at, "2026-10-12T04:00:00+00:00");
  assert.equal(await productStatus("nothing"), null);
  const door = withStatus("2026-10-01", st);
  assert.equal(door.stamp, "2026-10-12T04:00:00+00:00"); // what's new: the later of the data's stamp and the last change
  assert.equal(door.checked, st.checked_at); // is it alive
  assert.deepEqual(withStatus("2026-10-01", undefined), { stamp: "2026-10-01" });
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
