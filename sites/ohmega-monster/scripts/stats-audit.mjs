#!/usr/bin/env node
// Stats audit: one place to see every reader-facing number (docs/architecture/information-architecture.md section 4).
//   node scripts/stats-audit.mjs          list the registry, then the findings
//   node scripts/stats-audit.mjs --json   the same as JSON
// Reads lib/stats/registry.ts as TEXT (no TypeScript toolchain, no installs). It reports:
//   1. every registered stat: id, basis, baseline_since, min_history, surfaces        (informational)
//   2. surfaces named in the registry that do not exist                                (error: the registry lies)
//   3. ids used in code (statView / <Stat> / statDef) that are not registered          (error: it would throw at render)
//   4. registered ids no code uses yet                                                 (informational)
//   5. components and routes that render numbers by hand (toFixed / toLocaleString / Math.round in JSX/template text)
//      but neither import lib/stats nor are named as a registry surface                (informational: the unregistered renders)
// Exit code 1 only for 2 and 3 (real bugs); 4 and 5 are soft pressure, per docs/linting/static-governance.md.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const exists = (p) => fs.existsSync(path.join(ROOT, p));

// ---- registry (text parse of the STATS array: each entry is a `def({ ... })` call) ---------------------------------------------
const reg = read("lib/stats/registry.ts");
const body = reg.slice(reg.indexOf("export const STATS"), reg.indexOf("const BY_ID"));
const entries = body.split(/\n\s*def\(\{/).slice(1).map((chunk) => {
  const pick = (re) => (re.exec(chunk) ?? [])[1] ?? null;
  const surfaces = [...(/surfaces:\s*\[([^\]]*)\]/.exec(chunk)?.[1] ?? "").matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  return {
    id: pick(/\bid:\s*"([^"]+)"/),
    basis: pick(/\bbasis:\s*"([^"]+)"/),
    baseline_since: pick(/\bbaseline_since:\s*"([^"]+)"/),
    min_history: pick(/\bmin_history:\s*(\w+)/),
    surfaces,
  };
});
const ids = new Set(entries.map((e) => e.id));

// ---- source walk ------------------------------------------------------------------------------------------------------------
const SKIP = new Set(["node_modules", ".next", "content", "public", "scripts"]);
function walk(dir, out = []) {
  for (const name of fs.readdirSync(path.join(ROOT, dir), { withFileTypes: true })) {
    if (SKIP.has(name.name)) continue;
    const rel = path.posix.join(dir, name.name);
    if (name.isDirectory()) walk(rel, out);
    else if (/\.(ts|tsx)$/.test(name.name)) out.push(rel);
  }
  return out;
}
const files = ["app", "components", "lib"].flatMap((d) => walk(d));
const text = new Map(files.map((f) => [f, read(f)]));

// ids used in code
const used = new Map(); // id -> files
for (const [f, src] of text) {
  if (f === "lib/stats/registry.ts") continue;
  for (const m of src.matchAll(/(?:statView|statDef)\(\s*\{?\s*(?:id:\s*)?"([a-z0-9_]+)"/g)) (used.get(m[1]) ?? used.set(m[1], new Set()).get(m[1])).add(f);
  for (const m of src.matchAll(/<Stat\b[^>]*\bid="([a-z0-9_]+)"/g)) (used.get(m[1]) ?? used.set(m[1], new Set()).get(m[1])).add(f);
}
const unknownIds = [...used.keys()].filter((i) => !ids.has(i)).map((i) => ({ id: i, files: [...used.get(i)] }));
const unusedIds = entries.filter((e) => !used.has(e.id)).map((e) => e.id);

// surfaces that do not exist (a surface may be a file, a directory or an extensionless route path)
const missingSurfaces = entries.flatMap((e) => e.surfaces.filter((s) => !exists(s) && !exists(`${s}.ts`) && !exists(`${s}.tsx`)).map((s) => ({ id: e.id, surface: s })));

// hand-rendered numbers outside the registry
const surfaceSet = new Set(entries.flatMap((e) => e.surfaces));
const covered = (f) => surfaceSet.has(f) || [...surfaceSet].some((s) => f.startsWith(`${s}/`)) || /lib\/stats\//.test(read(f)) && /from "@\/lib\/stats|from "\.\/stats/.test(read(f));
const NUMERIC = /\.toFixed\(|\.toLocaleString\(|Math\.round\(|fmtNum\(|\bpct\(/;
const hand = files
  .filter((f) => /\.tsx$/.test(f) || /^lib\/(glance|globe-hud|sections)\.ts$/.test(f))
  .filter((f) => NUMERIC.test(text.get(f)) && !covered(f))
  .map((f) => ({ file: f, renders: (text.get(f).match(new RegExp(NUMERIC.source, "g")) ?? []).length }))
  .sort((a, b) => b.renders - a.renders);

const report = { registered: entries, missingSurfaces, unknownIds, unusedIds, handRendered: hand };
if (process.argv.includes("--json")) {
  console.log(JSON.stringify(report, null, 2));
} else {
  const pad = (s, n) => String(s ?? "-").padEnd(n);
  console.log(`Registered stats (${entries.length})\n`);
  console.log(`${pad("id", 32)}${pad("basis", 12)}${pad("baseline_since", 16)}${pad("min_history", 12)}surfaces`);
  for (const e of entries) console.log(`${pad(e.id, 32)}${pad(e.basis, 12)}${pad(e.baseline_since, 16)}${pad(e.min_history, 12)}${e.surfaces.join(", ")}`);
  const section = (title, rows, fmt) => { console.log(`\n${title} (${rows.length})`); rows.forEach((r) => console.log(`  ${fmt(r)}`)); };
  section("ERROR  surfaces named in the registry that do not exist", missingSurfaces, (r) => `${r.id}: ${r.surface}`);
  section("ERROR  ids used in code but not registered", unknownIds, (r) => `${r.id}: ${r.files.join(", ")}`);
  section("info   registered ids no code uses yet", unusedIds, (r) => r);
  section("info   files that format numbers by hand and are not registry surfaces (candidates to register)", hand, (r) => `${r.file} (${r.renders})`);
}
process.exit(missingSurfaces.length + unknownIds.length > 0 ? 1 : 0);
