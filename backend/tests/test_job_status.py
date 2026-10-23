"""Per-product status files: checked_at (alive) apart from last_changed_at (new content), one PUT per successful run, throttled for fast products."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime, timedelta

from algent_backend.ops import status
from algent_backend.ops.products import run as products_run, views
from algent_backend.publishing import changed
from tests.jobq_fakes import queue

T0 = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


class Bucket:
    """The injectable transport of the uploaders: records every PUT."""

    def __init__(self) -> None:
        self.puts: list[tuple[str, bytes]] = []

    def __call__(self, method, url, headers, body):
        if method == "PUT":
            self.puts.append((url, body))
        return 200


def _doc(bucket: Bucket, n: int = -1) -> dict:
    return json.loads(gzip.decompress(bucket.puts[n][1]))


def test_a_successful_run_publishes_checked_at_and_keeps_last_changed_at_when_nothing_new_went_out() -> None:
    sanctions, bucket = views.by_id("sanctions"), Bucket()
    doc = status.record(sanctions, "sanctions", True, now=T0, http=bucket)
    assert doc["schema"] == "ohmega.status/1" and doc["checked_at"].startswith("2026-10-23T12:00") and doc["last_changed_at"] is None
    assert doc["last_ok"] is True and doc["cadence_min"] == 360 and doc["next_due"].startswith("2026-10-23T18:00")
    assert len(bucket.puts) == 1 and bucket.puts[0][0].endswith("/docs/status/sanctions.json.gz")


def test_last_changed_at_moves_only_when_a_run_really_uploaded_something(monkeypatch) -> None:
    sanctions, bucket = views.by_id("sanctions"), Bucket()
    monkeypatch.setenv(changed.ENV, "sanctions")
    changed.note(["sanctions/recent.json"], now=T0 - timedelta(days=11))
    monkeypatch.delenv(changed.ENV)
    status.record(sanctions, "sanctions", True, now=T0, http=bucket)
    a = _doc(bucket)
    status.record(sanctions, "sanctions", True, now=T0 + timedelta(hours=6), http=bucket)       # ran fine, no new designation
    b = _doc(bucket)
    assert a["last_changed_at"] == b["last_changed_at"] == (T0 - timedelta(days=11)).isoformat(timespec="seconds")
    assert b["checked_at"] > a["checked_at"], "the site can tell it is alive although nothing changed"
    assert len(bucket.puts) == 2


def test_notes_ignore_status_documents_staging_and_runs_outside_a_runner(monkeypatch) -> None:
    changed.note(["sanctions/recent.json"])                                                     # no runner: nothing recorded
    assert changed.last_change("sanctions") == ""
    monkeypatch.setenv(changed.ENV, "sanctions")
    changed.note(["status/sanctions.json", "_names/sanctions.json"])
    assert changed.last_change("sanctions") == ""
    monkeypatch.setenv("ALGENT_PUBLISH_TARGET", "staging")
    changed.note(["sanctions/recent.json"])
    assert changed.last_change("sanctions") == ""


def test_the_uploaders_note_what_they_really_sent(monkeypatch) -> None:
    from algent_backend.publishing import object_docs

    monkeypatch.setenv(changed.ENV, "sanctions")
    bucket = Bucket()
    assert object_docs.publish({"sanctions/recent.json": {"rows": []}}, http=bucket, names=False)["documents"] == 1
    first = changed.last_change("sanctions")
    assert first
    monkeypatch.setattr(changed, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: T0 + timedelta(days=1))}))
    assert object_docs.publish({"sanctions/recent.json": {"rows": []}}, http=bucket, names=False)["documents"] == 0    # hash-skipped
    assert changed.last_change("sanctions") == first


def test_a_failed_run_uploads_nothing_and_is_remembered_for_the_next_status() -> None:
    cal, bucket = views.by_id("calendar"), Bucket()
    status.record(cal, "calendar", True, now=T0, http=bucket)
    status.record(cal, "calendar", False, now=T0 + timedelta(days=1), http=bucket)
    assert len(bucket.puts) == 1
    status.record(cal, "calendar", True, now=T0 + timedelta(days=2), http=bucket)
    assert _doc(bucket)["last_failed_at"].startswith("2026-10-24T12:00")


def test_a_fast_product_publishes_its_status_at_most_every_half_hour() -> None:
    live, bucket = views.by_id("live"), Bucket()
    for minutes in (0, 10, 20, 31, 40, 62):
        status.record(live, "live-usgs", True, now=T0 + timedelta(minutes=minutes), http=bucket)
    assert len(bucket.puts) == 3                                                                # at 0, 31 and 62
    assert status.read_local("live")["checked_at"].startswith("2026-10-23T13:02"), "the local copy is always current"


def test_products_that_publish_nothing_or_are_staging_have_no_status() -> None:
    for pid in ("library", "corpus_index", "ops", "staging", "profiles"):
        assert status.record(views.by_id(pid), "x", True, now=T0, http=Bucket()) is None


def test_the_class_a_cost_is_a_fraction_of_a_percent_of_the_monthly_allowance() -> None:
    per_day = status.puts_per_day()
    assert "sanctions" in per_day and "staging" not in per_day and per_day["live"] <= 48
    assert sum(per_day.values()) * 30 < 0.01 * 1_000_000, per_day


def _run(monkeypatch, tmp_path, publish: bool):
    q, _env, _ledger = queue(tmp_path)
    monkeypatch.setattr(products_run, "make_queue", lambda: q)

    def call(cmd, cwd=None):
        if cmd[-2:] == ["sanctions", "fetch"] and publish:
            changed.note(["sanctions/recent.json"])
        return 0

    monkeypatch.setattr(products_run.measure, "call", call)
    return products_run.run_job("sanctions")


def test_the_job_runner_records_a_check_and_a_change_per_run(monkeypatch, tmp_path) -> None:
    assert _run(monkeypatch, tmp_path, publish=True) == 0
    first = status.read_local("sanctions")
    assert first["checked_at"] and first["last_changed_at"]
    assert _run(monkeypatch, tmp_path, publish=False) == 0
    second = status.read_local("sanctions")
    assert second["last_changed_at"] == first["last_changed_at"] and second["checked_at"] >= first["checked_at"]


def test_a_run_that_was_skipped_or_coalesced_is_not_a_check(monkeypatch, tmp_path) -> None:
    q, env, _ledger = queue(tmp_path)
    env.other_waits("sanctions", 3)                                                             # the same job is already waiting: this invocation coalesces
    monkeypatch.setattr(products_run, "make_queue", lambda: q)
    monkeypatch.setattr(products_run.measure, "call", lambda cmd, cwd=None: 0)
    assert products_run.run_job("sanctions") == 0
    assert status.read_local("sanctions") == {}
