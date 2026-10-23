// Smoke test of a deployed site:  node scripts/smoke.mjs <base URL> [--json]
//
// There is ONE implementation, in Python (backend/algent_backend/ops/smoke/), so the same checks run on the worker server (hourly against production, and
// after every publish job), in the backend's tests with a fake site, and here. This file is only the entry point for someone standing in the site folder: it
// starts that implementation and passes its exit code on (0 healthy, 1 a check failed, 2 usage).
//
// It reads the product registry (every page route), the site's own /sitemap.xml (a sample of each dynamic route), and calls /api/v1 (envelopes, freshness).
// A preview behind Vercel's deployment protection needs VERCEL_AUTOMATION_BYPASS_SECRET in the environment. Docs: docs/guides/deploy.md.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const backend = path.resolve(here, "../../../backend");
const venvPython = [path.join(backend, ".venv", "Scripts", "python.exe"), path.join(backend, ".venv", "bin", "python")].find(existsSync);
const python = process.env.PYTHON || venvPython || "python";

const args = process.argv.slice(2);
const base = args.find((a) => /^https?:\/\//.test(a));
if (!base) {
  console.error("usage: node scripts/smoke.mjs <base URL, e.g. https://algent-git-organic-dev.vercel.app> [--json]");
  process.exit(2);
}
const extra = args.includes("--json") ? ["--json"] : [];
const run = spawnSync(python, ["-m", "algent_backend.cli", "newsroom", "site", "smoke", "--base", base, ...extra], { cwd: backend, stdio: "inherit" });
process.exit(run.status ?? 2);
