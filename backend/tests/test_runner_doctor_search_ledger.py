"""Offline tests: runner claim/release/guard, newsroom doctor, search ledger + usage summary."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from algent_backend.agent_system.tools.sourcing.search import quota, search_ledger
from algent_backend.data_backup import runner, sync
from algent_backend.ops import doctor

_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- runner

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def machines(tmp_path, monkeypatch):
    """Two clones of one bare 'archive'; ``as_machine(name)`` switches which machine the code believes it is."""
    for k, v in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                 "GIT_COMMITTER_EMAIL": "t@t"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("ALGENT_DATA_BACKUP", "1")
    monkeypatch.delenv("ALGENT_RUNNER_GUARD", raising=False)
    bare = tmp_path / "bare.git"
    _git(tmp_path, "init", "--bare", "--initial-branch=main", str(bare))
    clones = {}
    for name in ("server", "laptop"):
        wt = tmp_path / name
        _git(tmp_path, "clone", str(bare), str(wt))
        _git(wt, "checkout", "-B", "main")
        clones[name] = wt
    current = {"name": "server"}

    def fake_checkout():
        wt = clones[current["name"]]
        sync._git(wt, "pull", "--ff-only", "origin", "main")      # empty remote on first use: harmless
        return wt, "updated"

    monkeypatch.setattr(sync, "_checkout", fake_checkout)

    def as_machine(name):
        current["name"] = name
        monkeypatch.setenv("ALGENT_RUNNER_NAME", name)

    as_machine("server")
    return as_machine


def test_claim_release_handover_and_guard(machines):
    assert runner.refusal("publish") is None                    # nobody holds it: allowed
    assert runner.claim()["claimed"] is True
    assert runner.status()["is_runner"] is True
    assert runner.refusal("publish") is None

    machines("laptop")
    assert runner.status()["runner"] == "server"
    msg = runner.refusal("publish")
    assert msg and "server is the runner" in msg and "--force" in msg
    refused = runner.claim()
    assert refused["claimed"] is False and "--force" in refused["note"]
    assert runner.release()["released"] is False                # not the holder

    machines("server")
    assert runner.release()["released"] is True
    machines("laptop")
    assert runner.claim()["claimed"] is True
    assert runner.refusal("publish") is None
    machines("server")
    assert runner.refusal("run paid work")                      # roles swapped


def test_force_takes_over_a_dead_holder(machines):
    runner.claim()
    machines("laptop")
    out = runner.claim(force=True)
    assert out["claimed"] is True
    rec = json.loads((sync._checkout()[0] / runner.FILENAME).read_text())
    assert rec["host"] == "laptop" and rec["took_over_from"] == "server"


def test_guard_fails_open_and_can_be_disabled(machines, monkeypatch):
    runner.claim()
    machines("laptop")
    assert runner.refusal("publish")
    monkeypatch.setenv("ALGENT_RUNNER_GUARD", "0")
    assert runner.refusal("publish") is None
    monkeypatch.delenv("ALGENT_RUNNER_GUARD")
    monkeypatch.setattr(sync, "_checkout", lambda: (None, "clone failed"))   # archive unreachable
    assert runner.refusal("publish") is None
    assert runner.claim()["claimed"] is False                    # but never claims blind


def test_publish_run_refuses_on_non_runner(machines, tmp_path):
    from algent_backend.publishing import publish as pb

    runner.claim()
    machines("laptop")
    res = pb.publish_run(tmp_path, site_dir=tmp_path / "s", held_dir=tmp_path / "h")
    assert res.action == "error" and "server is the runner" in res.reasons[0]


# ---------------------------------------------------------------- doctor

class FakeProbes(doctor.Probes):
    def __init__(self, **kw):
        self.kw = kw

    def db_select1(self):
        if "db_error" in self.kw:
            raise RuntimeError(self.kw["db_error"])

    def http_get_json(self, url, timeout=10.0):
        if self.kw.get("searxng_down"):
            raise ConnectionError("refused")
        return {"results": [{"url": "x"}]}

    def engine_query(self, name):
        if name in self.kw.get("dead_engines", ()):
            raise RuntimeError("blocked")
        return 3

    def playwright_importable(self):
        return True

    def free_read(self):
        return {"via": "trafilatura", "quality": "good"}

    def which(self, name):
        return f"/bin/{name}"

    def run(self, cmd, timeout=20.0, cwd=None):
        if cmd[0].endswith("codex"):
            return 0, "Logged in"
        if cmd[0] == "git":
            return 0, "abc\trefs/heads/site-live"
        return 0, "grok 1.2.3"

    def runner_status(self):
        return {"runner": "box", "is_runner": True, "this_host": "box", "reachable": True, "since": "t"}

    def quota_summary(self):
        return {"tavily": {"used": 790, "cap": 800}, "exa": {"used": 0, "cap": 300}}

    def disk_free_gb(self):
        return 50.0

    def mem_available_mb(self):
        return 2000.0


_FULL_ENV = {"META_MODEL_API_KEY": "m-secret-123456", "META_MODEL_API_BASE_URL": "https://m", "GEMINI_API_KEY": "g",
             "X_BEARER_TOKEN": "x", "X_API_KEY": "a", "X_API_KEY_SECRET": "b", "X_ACCESS_TOKEN": "c",
             "X_ACCESS_TOKEN_SECRET": "d", "X_POST_HANDLE": "h", "ALGENT_DB_PUBLISH": "0",
             "DATABASE_URL": "postgresql://u:pw-secret@host:5432/db"}


def test_doctor_all_green_and_key_names_only():
    rep = doctor.run_checks(_FULL_ENV, FakeProbes())
    assert rep["ok"] is True
    assert rep["checks"]["database"]["status"] == "ok"
    assert rep["checks"]["quota:tavily"]["status"] == "warn"          # 790/800 is past 80%
    assert rep["checks"]["publish"]["status"] == "ok"
    blob = json.dumps(rep)
    assert "m-secret-123456" not in blob and "pw-secret" not in blob
    assert "summary" in rep and "fail" in rep["summary"]


def test_doctor_scrubs_connection_errors_and_flags_missing_keys():
    env = {**_FULL_ENV}
    del env["META_MODEL_API_KEY"]
    rep = doctor.run_checks(env, FakeProbes(db_error="could not connect to postgresql://u:pw-secret@host/db"))
    db = rep["checks"]["database"]
    assert db["status"] == "fail" and "pw-secret" not in json.dumps(rep) and "postgres" not in db["detail"]
    assert rep["checks"]["key:house model key"]["status"] == "fail"
    assert rep["ok"] is False


def test_doctor_search_degradation(tmp_path):
    rep = doctor.run_checks(_FULL_ENV, FakeProbes(searxng_down=True, dead_engines=("ddg", "bing", "gnews")))
    assert rep["checks"]["searxng"]["status"] == "warn"
    assert rep["checks"]["search:summary"]["status"] == "fail"
    # engine answers are cached: a second run makes no new request even if probes now would fail
    rep2 = doctor.run_checks(_FULL_ENV, FakeProbes(searxng_down=True))
    assert "(cached)" in rep2["checks"]["engine:ddg"]["detail"]


def test_scrub_withholds_urls_and_redacts_values():
    assert "withheld" in doctor.scrub("failed postgres://x")
    assert "withheld" in doctor.scrub("user@host")
    assert "tok-12345678" not in doctor.scrub("bad tok-12345678", {"X_TOKEN": "tok-12345678"})


def test_doctor_key_names_are_in_the_manifest():
    manifest = (_ROOT / "docs" / "credentials.md").read_text(encoding="utf-8")
    names = [n for _l, alts, _s in doctor.REQUIRED_KEYS for n in alts] + list(doctor.OPTIONAL_KEYS)
    assert [n for n in names if n not in manifest] == []


# ---------------------------------------------------------------- search ledger

def test_ledger_line_has_no_query_text(tmp_path):
    search_ledger.record_result("keyword", "secret query words", {"provider": "ddg", "results": [1, 2]},
                                ["searxng", "ddg", "bing"], cached=False, elapsed_ms=120)
    line = search_ledger.ledger_path().read_text(encoding="utf-8")
    row = json.loads(line)
    assert "secret" not in line and row["qlen"] == 18
    assert row["provider"] == "ddg" and row["tried"] == ["searxng", "ddg"] and row["n"] == 2 and row["ms"] == 120


def test_facade_writes_a_ledger_line(monkeypatch):
    from algent_backend.agent_system.tools.sourcing.search import research

    monkeypatch.setattr(research, "_search_web", lambda q, k, n: {"provider": "searxng", "results": [1]})
    monkeypatch.setattr(research.read_cache, "get_search", lambda k, q: None)
    monkeypatch.setattr(research.read_cache, "put_search", lambda k, q, r: None)
    research._search(query="hello there", kind="keyword")
    row = json.loads(search_ledger.ledger_path().read_text().splitlines()[-1])
    assert row["provider"] == "searxng" and row["kind"] == "keyword" and "hello" not in json.dumps(row)


def test_usage_summary_math():
    now = datetime.now(UTC)
    for provider, tried, n, ms, cached in [
        ("searxng", ["searxng"], 5, 100, False), ("searxng", ["searxng"], 4, 300, False),
        ("ddg", ["searxng", "ddg"], 3, 200, False), ("tavily", ["searxng", "ddg", "bing", "tavily"], 2, 900, False),
        ("none", ["searxng", "ddg"], 0, 50, False), ("searxng", ["searxng"], 5, 0, True),
    ]:
        search_ledger.record(kind="keyword", provider=provider, tried=tried, cached=cached, results=n,
                             elapsed_ms=ms, query_len=5)
    s = search_ledger.summarise(7, now=now)
    assert s["searches"] == 6 and s["cached"] == 1 and s["live"] == 5
    assert s["by_provider"]["searxng"] == {"n": 2, "share_pct": 40.0, "avg_ms": 200}
    assert s["free_share_pct"] == 60.0 and s["paid_share_pct"] == 20.0
    assert s["failure_rate_pct"] == 20.0 and s["fell_through_pct"] == 40.0
    assert s["paid_quota_this_month"].keys() == quota.MONTHLY_CAPS.keys()
