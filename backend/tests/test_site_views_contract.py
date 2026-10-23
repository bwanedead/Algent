"""The contract between the server's views and the site's readers: build every view from the fixture record, then run the site's own lib code (TypeScript, transpiled
on the fly) against them through a fake bucket - sites/ohmega-monster/scripts/view-check.mjs. It needs node and the `typescript` package (``npm install`` in
sites/ohmega-monster once, or TYPESCRIPT_PATH); without them the test skips, and the Python side of the contract is still covered by test_views_*.py."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from views_fixture import context

from algent_backend.corpus.sink import Sink
from algent_backend.views import build

SITE = Path(__file__).resolve().parents[2] / "sites" / "ohmega-monster"


def typescript() -> str | None:
    env = os.environ.get("TYPESCRIPT_PATH")
    if env and Path(env).exists():
        return env
    local = SITE / "node_modules" / "typescript" / "lib" / "typescript.js"
    return str(local) if local.exists() else None


def fixture_views(tmp_path: Path) -> dict[str, dict]:
    ctx = context(tmp_path, with_corpus=True)
    ctx.corpus.db.isolation_level = None
    s = Sink(ctx.corpus.db, "actors", "ind:gdp2", "2026-10-23T00:00:00+00:00")
    for iso, base in (("country:US", 2.5e13), ("country:FR", 3e12)):
        for y in range(2020, 2025):
            s.observation("gdp", str(y), base + y, entity=iso, unit="usd", basis="official", label="GDP")
    ctx.tables._docs["geo/a/plant1.json"] = {
        "asset": {"id": "plant1", "name": "Bandar Abbas power plant", "aliases": [], "type": "power_plant", "country": "IR", "lat": 27.1, "lon": 56.2, "loc_precision": "exact",
                  "capacity_mw": 500, "fuel": "gas", "attrs": {}, "source": "wri", "licence": "CC BY", "provenance": "aggregated", "status": "damaged", "status_on": "2026-10-21",
                  "status_by": "Iran", "events": 1, "merged_into": None},
        "events": [{"id": "e1", "asset_id": "plant1", "occurred_on": "2026-10-21", "occurred_at": "", "status": "reported_damaged", "claimant": "Iran", "confidence": "medium",
                    "sources": ["https://example.org/x"], "provenance": "aggregated", "observed_at": "2026-10-22", "note": "", "via": "daily:2026-10-21:thr_hormuz"}]}
    res = build.build_all(ctx)
    assert not res.errors, res.errors
    return {v.key: v.body for v in res.views}


def test_the_site_reads_what_the_server_builds(tmp_path):
    node, ts = shutil.which("node"), typescript()
    if not node or not ts:
        pytest.skip("node and the `typescript` package are needed (npm install in sites/ohmega-monster, or set TYPESCRIPT_PATH)")
    path = tmp_path / "views.json"
    path.write_text(json.dumps(fixture_views(tmp_path)), encoding="utf-8")
    run = subprocess.run([node, str(SITE / "scripts" / "view-check.mjs"), str(path)], capture_output=True, text=True, encoding="utf-8", timeout=180,
                         env={**os.environ, "TYPESCRIPT_PATH": ts}, cwd=str(SITE))
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.count("ok   ") >= 7 and "FAIL" not in run.stdout
