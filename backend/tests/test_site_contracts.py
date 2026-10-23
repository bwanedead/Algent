"""The contract between the server's documents and the site's parsers, in both directions: the typed examples (``contracts/examples.py``, which the backend tests hold to the
shapes and the writers) are served from a fake bucket to the site's own readers - sites/ohmega-monster/scripts/contract-check.mjs. A field renamed on the server side
fails ``test_contracts.py``; one renamed in a TypeScript parser fails here. Needs node and the `typescript` package (``npm install`` in sites/ohmega-monster, or
TYPESCRIPT_PATH); without them the test skips."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest
from test_site_views_contract import SITE, typescript

from algent_backend.contracts.examples import EXAMPLES


def run_check(tmp_path, docs):
    path = tmp_path / "docs.json"
    path.write_text(json.dumps(docs), encoding="utf-8")
    return subprocess.run([shutil.which("node"), str(SITE / "scripts" / "contract-check.mjs"), str(path)], capture_output=True, text=True, encoding="utf-8", timeout=180,
                          env={**os.environ, "TYPESCRIPT_PATH": typescript()}, cwd=str(SITE))


def test_the_site_reads_every_example_through_its_own_parsers(tmp_path):
    if not shutil.which("node") or not typescript():
        pytest.skip("node and the `typescript` package are needed (npm install in sites/ohmega-monster, or set TYPESCRIPT_PATH)")
    run = run_check(tmp_path, {path: doc for path, doc in EXAMPLES.values()})
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.count("ok   ") == 8 and "FAIL" not in run.stdout


def test_a_renamed_field_is_caught_by_the_site_side_check(tmp_path):
    if not shutil.which("node") or not typescript():
        pytest.skip("node and the `typescript` package are needed")
    docs = {path: json.loads(json.dumps(doc)) for path, doc in EXAMPLES.values()}
    for row in docs["sanctions/recent.json"]["rows"]:
        row["designation"] = row.pop("name")                                                                       # the rename
    run = run_check(tmp_path, docs)
    assert run.returncode == 1 and "FAIL sanctions, calendar, maritime" in run.stdout
