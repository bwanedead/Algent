"""`newsroom envelope`: every register row measured and judged against the budgets in envelope_flags. Offline, fake probes."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from algent_backend.ops import doctor, envelope, envelope_flags as f
from algent_backend.ops.products import views
from algent_backend.ops.products.model import Budget

NOW = datetime(2026, 10, 23, 7, 10, tzinfo=UTC)


class FakeProbes(envelope.Probes):
    def __init__(self, tmp: Path, **kw) -> None:
        self.tmp, self.kw = tmp, kw

    def disk(self):
        return self.kw.get("disk", (40.0, 77.0))

    def mem_available_mb(self):
        return self.kw.get("mem", 1800.0)

    def journal_mb(self):
        return self.kw.get("journal", 190.0)

    def store_roots(self):
        return self.kw.get("roots", {})

    def r2_status(self):
        return self.kw.get("r2", {"month": "2026-10", "level": "ok", "usage": {
            "class_a": {"share": 0.006, "projected_share": 0.02}, "class_b": {"share": 0.001}, "storage_bytes": {"used": 7e7, "share": 0.007}}})

    def snapshot_state(self):
        return self.kw.get("snap", {"state": {"last_snapshot": {"date": "2026-10-23", "files": 900}, "last_drill": {"ok": True, "snapshot": "2026-10-01", "files": 900}},
                                    "age_h": 1.0, "drill_age_days": 20.0})

    def feed_rows(self):
        return self.kw.get("feeds", [{"feed": "usgs", "needs": "", "last_ok": NOW.isoformat()}])

    def feed_cadence_min(self, feed):
        return 15.0

    def search_results(self, base):
        return self.kw.get("search", 30)

    def smoke_state(self):
        return self.kw.get("smoke", {"at": NOW.isoformat(), "ok": True, "summary": "58 checks: 58 ok, 0 warn, 0 fail; p95 900 ms"})

    def spend_by_day(self):
        return self.kw.get("spend", {"2026-10-23": 1.5})

    def state_path(self):
        return self.tmp / "envelope_state.json"


def run(tmp_path, skip=(), **kw):
    return envelope.run({}, FakeProbes(tmp_path, **kw), NOW, skip=skip)


def test_a_healthy_box_is_all_ok_and_logs_one_line(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    rep = run(tmp_path)
    assert rep["ok"] and rep["summary"] == "11 ok, 0 warn, 0 fail"
    assert set(rep["rows"]) == {"disk", "memory", "journald", "r2", "backup", "restore_drill", "feeds", "search", "site", "spend_day", "spend_month"}
    line = envelope.one_line(rep)
    assert line.startswith("envelope all 11 rows ok") and "\n" not in line
    envelope.log(rep)
    assert "envelope all 11 rows ok" in (tmp_path / "ops-log.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("kw,row,status", [
    ({"disk": (8.0, 77.0)}, "disk", "warn"), ({"disk": (2.0, 77.0)}, "disk", "fail"),
    ({"mem": 400.0}, "memory", "warn"), ({"mem": 100.0}, "memory", "fail"),
    ({"journal": 562.0}, "journald", "fail"), ({"journal": 300.0}, "journald", "warn"), ({"journal": None}, "journald", "warn"),
    ({"r2": {"month": "m", "level": "warn", "usage": {"class_a": {"share": 0.75, "projected_share": 1.0}, "class_b": {"share": 0.0}, "storage_bytes": {"used": 1, "share": 0.0}}}}, "r2", "warn"),
    ({"snap": {"state": {}, "age_h": None, "drill_age_days": None}}, "backup", "fail"),
    ({"snap": {"state": {"last_snapshot": {}}, "age_h": 40.0, "drill_age_days": 1.0}}, "backup", "warn"),
    ({"snap": {"state": {"last_snapshot": {}}, "age_h": 80.0, "drill_age_days": 1.0}}, "backup", "fail"),
    ({"snap": {"state": {"last_snapshot": {}, "last_drill": {"ok": False, "problems": ["x differs"]}}, "age_h": 1.0, "drill_age_days": 2.0}}, "restore_drill", "fail"),
    ({"snap": {"state": {"last_snapshot": {}}, "age_h": 1.0, "drill_age_days": None}}, "restore_drill", "warn"),
    ({"snap": {"state": {"last_snapshot": {}, "last_drill": {"ok": True}}, "age_h": 1.0, "drill_age_days": 60.0}}, "restore_drill", "warn"),
    ({"search": 3}, "search", "warn"), ({"search": 0}, "search", "fail"),
    ({"spend": {"2026-10-23": 25.0}}, "spend_day", "warn"), ({"spend": {"2026-10-23": 41.0}}, "spend_day", "fail"),
])
def test_each_row_is_judged_against_its_budget(tmp_path, kw, row, status) -> None:
    assert run(tmp_path, **kw)["rows"][row]["status"] == status


def test_stores_report_size_and_seven_day_writes(tmp_path) -> None:
    root = tmp_path / "maritime_store"
    root.mkdir()
    (root / "old.bin").write_bytes(b"x" * 2_000_000)
    os.utime(root / "old.bin", (time.time() - 30 * 86400,) * 2)
    (root / "new.bin").write_bytes(b"x" * 1_000_000)
    other = tmp_path / "pulse_store"
    other.mkdir()
    (other / "a").write_bytes(b"1")
    rep = run(tmp_path, roots={"maritime_store": root, "pulse_store": other, "ghost_store": tmp_path / "nope"})
    m = rep["rows"]["store:maritime_store"]
    assert m["status"] == "ok" and m["mb"] == pytest.approx(2.9, abs=0.1) and m["written_7d_mb"] == pytest.approx(0.95, abs=0.1)
    assert "store:ghost_store" not in rep["rows"]                                       # not on this machine: no row


def test_a_store_over_budget_or_churning_is_flagged(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(views, "budget_for", lambda name: Budget(1, 1, 5, 1.5, 0, "test budget") if name == "maritime_store" else None)
    root = tmp_path / "maritime_store"
    root.mkdir()
    (root / "log").write_bytes(b"x" * 2_000_000)
    assert run(tmp_path, roots={"maritime_store": root})["rows"]["store:maritime_store"]["status"] == "warn"      # size past warn
    (root / "log").write_bytes(b"x" * 6_000_000)
    assert run(tmp_path, roots={"maritime_store": root})["rows"]["store:maritime_store"]["status"] == "fail"


def test_feeds_stale_is_a_warning_most_stale_is_a_failure(tmp_path) -> None:
    old = "2026-10-22T00:00:00+00:00"
    one = [{"feed": "a", "needs": "", "last_ok": NOW.isoformat()}, {"feed": "b", "needs": "", "last_ok": NOW.isoformat()}, {"feed": "c", "needs": "", "last_ok": NOW.isoformat()},
           {"feed": "d", "needs": "", "last_ok": old}, {"feed": "k", "needs": "needs a key", "last_ok": ""}]
    assert run(tmp_path, feeds=one)["rows"]["feeds"]["status"] == "warn"
    most = [{"feed": "a", "needs": "", "last_ok": old}, {"feed": "b", "needs": "", "last_ok": ""}, {"feed": "c", "needs": "", "last_ok": NOW.isoformat()}]
    assert run(tmp_path, feeds=most)["rows"]["feeds"]["status"] == "fail"


def test_month_spend_survives_the_heartbeat_retention(tmp_path) -> None:
    run(tmp_path, spend={"2026-10-20": 2.0, "2026-10-21": 3.0, "2026-10-23": 1.0})
    later = run(tmp_path, spend={"2026-10-23": 1.5, "2026-10-24": 0.5})                  # the old heartbeats are gone, the state keeps them
    row = later["rows"]["spend_month"]
    assert row["value"] == pytest.approx(7.0) and later["rows"]["spend_day"]["value"] == 1.5
    assert json.loads((tmp_path / "envelope_state.json").read_text(encoding="utf-8"))["spend_days"]["2026-10-20"] == 2.0


def test_a_failing_probe_is_a_warning_not_a_crash(tmp_path) -> None:
    class Boom(FakeProbes):
        def journal_mb(self):
            raise RuntimeError("no access")

    rep = envelope.run({}, Boom(tmp_path), NOW)
    assert rep["rows"]["journald"]["status"] == "warn" and "could not measure" in rep["rows"]["journald"]["detail"] and "disk" in rep["rows"]


def test_the_doctor_embeds_only_the_rows_it_lacks(tmp_path) -> None:
    class P(doctor.Probes):
        envelope_probes = FakeProbes(tmp_path, roots={}, smoke={"at": datetime.now(UTC).isoformat(), "ok": True, "summary": "x"})

    out = doctor.check_envelope({}, P())
    assert set(out) == {"envelope:journald", "envelope:backup", "envelope:restore_drill", "envelope:site", "envelope:spend_day", "envelope:spend_month"}
    assert all(v["status"] == "ok" for v in out.values())


def test_every_store_budget_comes_from_the_registry_and_is_measured() -> None:
    """The envelope has no budget table of its own: its store rows are the registry's budgeted stores."""
    assert not hasattr(f, "STORE_MB")
    assert set(envelope.Probes().store_roots()) == {s.name for _, s in views.stores() if s.budget}
    assert views.budget_for("maritime_store").fail_mb == 3000 and views.budget_for("nope") is None


def test_the_site_row_follows_the_last_smoke_test(tmp_path) -> None:
    assert run(tmp_path)["rows"]["site"]["status"] == "ok"
    failing = run(tmp_path, smoke={"at": NOW.isoformat(), "ok": False, "since_failure": "2026-10-23T05:00:00+00:00", "failing": ["/pulses: status 500"]})["rows"]["site"]
    assert failing["status"] == "fail" and "/pulses: status 500" in failing["detail"]
    late = run(tmp_path, smoke={"at": "2026-10-23T02:00:00+00:00", "ok": True, "summary": "x"})["rows"]["site"]
    assert late["status"] == "warn" and "5.2 h ago" in late["detail"]
    assert run(tmp_path, smoke={})["rows"]["site"]["status"] == "warn"                            # never run: unknown, not green
