"""`newsroom products check`: the live machine judged against the registry, with fake probes. Offline."""

from __future__ import annotations

import os
import time
from pathlib import Path

from algent_backend.ops import doctor
from algent_backend.ops.products import check, views
from algent_backend.ops.products.model import Budget


class FakeProbes(check.Probes):
    def __init__(self, tmp: Path, **kw) -> None:
        self.tmp, self.kw = tmp, kw

    def installed_timers(self):
        return self.kw.get("timers", {j.name for _, j in views.timers()})

    def timer_state(self, job):
        return self.kw.get("state", "enabled")

    def snapshot_state(self):
        return self.kw.get("snap", {"state": {"last_snapshot": {"date": "2026-10-23", "by_store": {n: {} for n in views.backup_sources()}}}, "age_h": 1.0, "drill_age_days": 1.0})

    def store_roots(self):
        return self.kw.get("roots", {})


def _env(monkeypatch, tmp: Path) -> None:
    for _p, s in views.stores():
        if s.env:
            monkeypatch.setenv(s.env, str(tmp / s.env))


def test_registry_row_is_ok_and_reports_a_broken_registry(monkeypatch) -> None:
    assert check.row_registry()["status"] == "ok"
    monkeypatch.setattr(check.validate, "validate", lambda: ["pulses: no retention policy"])
    assert check.row_registry()["status"] == "fail"


def test_timers_missing_disabled_and_orphan(tmp_path) -> None:
    names = {j.name for _, j in views.timers()}
    assert check.row_timers(FakeProbes(tmp_path))["status"] == "ok"
    assert check.row_timers(FakeProbes(tmp_path, timers=names - {"sanctions"}))["detail"].startswith("not installed: sanctions")
    orphan = check.row_timers(FakeProbes(tmp_path, timers=names | {"old-experiment"}))
    assert orphan["status"] == "warn" and "old-experiment" in orphan["detail"]
    assert check.row_timers(FakeProbes(tmp_path, state="disabled"))["status"] == "warn"
    assert check.row_timers(FakeProbes(tmp_path, timers=None))["status"] == "ok"            # no systemd: the laptop


def test_an_irreplaceable_store_with_files_missing_from_the_snapshot_fails(tmp_path, monkeypatch) -> None:
    _env(monkeypatch, tmp_path)
    (tmp_path / "ALGENT_PULSE_STORE").mkdir()
    (tmp_path / "ALGENT_PULSE_STORE" / "log.jsonl").write_text("1\n", encoding="utf-8")
    assert check.row_snapshot(FakeProbes(tmp_path))["status"] == "ok"
    gap = {"state": {"last_snapshot": {"date": "2026-10-22", "by_store": {"profile_store": {}}}}, "age_h": 1.0, "drill_age_days": 1.0}
    row = check.row_snapshot(FakeProbes(tmp_path, snap=gap))
    assert row["status"] == "fail" and "pulse_store" in row["detail"]
    never = {"state": {}, "age_h": None, "drill_age_days": None}
    assert check.row_snapshot(FakeProbes(tmp_path, snap=never))["status"] == "warn"


def test_a_missing_store_is_a_warning_naming_it(tmp_path, monkeypatch) -> None:
    _env(monkeypatch, tmp_path)
    (tmp_path / "ALGENT_PULSE_STORE").mkdir()
    row = check.row_stores(FakeProbes(tmp_path))
    assert row["status"] == "warn" and "intel_store" in row["detail"] and "pulse_store" not in row["detail"]


def test_freshness_is_judged_against_the_slowest_cadence(tmp_path, monkeypatch) -> None:
    _env(monkeypatch, tmp_path)
    root = tmp_path / "ALGENT_SANCTIONS_STORE"
    root.mkdir()
    status = root / "status.json"
    status.write_text("{}", encoding="utf-8")
    now = time.time()
    assert check.row_fresh(FakeProbes(tmp_path), now)["status"] == "ok"                      # fetched just now (6 h cadence)
    stale = now - 3 * 3600 * 6 - 3600
    os.utime(status, (stale, stale))
    row = check.row_fresh(FakeProbes(tmp_path), now)
    assert row["status"] == "warn" and "sanctions" in row["detail"]
    status.unlink()
    assert "no status.json" in check.row_fresh(FakeProbes(tmp_path), now)["detail"]


def test_budgets_fold_the_envelope_store_rows(tmp_path, monkeypatch) -> None:
    root = tmp_path / "maritime_store"
    root.mkdir()
    (root / "log").write_bytes(b"x" * 4_000_000)
    monkeypatch.setattr(views, "budget_for", lambda name: Budget(1, 1, 3, 100, 0, "test budget") if name == "maritime_store" else None)
    row = check.row_budgets(FakeProbes(tmp_path, roots={"maritime_store": root}))
    assert row["status"] == "fail" and "maritime_store" in row["detail"]
    assert check.row_budgets(FakeProbes(tmp_path))["status"] == "ok"


def test_run_is_one_report_and_a_failing_row_does_not_blank_it(tmp_path, monkeypatch) -> None:
    rep = check.run(FakeProbes(tmp_path))
    assert set(rep["rows"]) == {f"products:{n}" for n in ("registry", "stores", "timers", "snapshot", "fresh", "budgets")}

    class Boom(FakeProbes):
        def installed_timers(self):
            raise RuntimeError("no systemctl")

    out = check.run(Boom(tmp_path), skip=("budgets",))
    assert out["rows"]["products:timers"]["status"] == "warn" and "could not measure" in out["rows"]["products:timers"]["detail"]
    assert "products:budgets" not in out["rows"] and "products:registry" in out["rows"]


def test_the_doctor_embeds_the_products_rows_but_not_budgets(tmp_path) -> None:
    class P(doctor.Probes):
        products_probes = FakeProbes(tmp_path)

    out = doctor.check_products({}, P())
    assert set(out) == {f"products:{n}" for n in ("registry", "stores", "timers", "snapshot", "fresh")}
