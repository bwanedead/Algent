"""The free-plan database budget (docs/architecture/database-budget.md): size verdicts, retention selection, the diet, the doctor line. No database."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("legacy_supabase")

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from algent_backend.database import diet, flags, prune, size
from algent_backend.publishing import doc_store


# ── a scripted fake connection ───────────────────────────────────────────────────────────────────
class Cur:
    def __init__(self, conn):
        self.c = conn
        self.rowcount = 0
        self._row = None
        self._rows: list = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        c, text = self.c, " ".join(sql.split())
        c.log.append((text, params))
        table = (re.search(r"(?:delete from|from) (\w+)", text) or [None, ""])[1]
        if text.startswith("select count(*)"):
            self._row = (c.remaining.get(self._table_of(text), 0),)
        elif text.startswith("delete from"):
            t = text.split()[2]
            n = min(flags.PRUNE_BATCH, c.remaining.get(t, 0))
            c.remaining[t] = c.remaining.get(t, 0) - n
            self.rowcount = n
        elif "pg_database_size" in text:
            self._row = (c.db_bytes,)
        elif "from pg_class" in text:
            self._rows = c.tables
        elif "storage.objects" in text:
            self._rows = c.storage
        elif "pg_ls_waldir" in text:
            if c.wal is None:
                raise RuntimeError("permission denied for function pg_ls_waldir")
            self._row = (c.wal,)
        elif text.startswith("select path, pg_column_size"):
            self._rows = [(p, len(str(b))) for p, b in sorted(c.inline.items())]
        elif text.startswith("select body from published_intel_documents"):
            self._row = (c.inline.get(params[0]),) if params[0] in c.inline else None
        elif text.startswith("update published_intel_documents"):
            key, nbytes, sha, path = params
            c.inline.pop(path, None)
            c.moved[path] = (key, nbytes, sha)
        del table

    @staticmethod
    def _table_of(text: str) -> str:
        m = re.search(r"from (\w+)(?: where|\)| )", text.split("select count(*) from (", 1)[1])
        return m.group(1) if m else ""

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class Conn:
    def __init__(self, remaining=None, db_bytes=0, tables=(), wal=None, inline=None, storage=()):
        self.log: list = []
        self.remaining = dict(remaining or {})
        self.db_bytes, self.tables, self.wal, self.storage = db_bytes, list(tables), wal, list(storage)
        self.inline = dict(inline or {})
        self.moved: dict = {}
        self.commits = 0
        self.rollbacks = 0
        self.autocommit = False
        self.autocommit_seen: list[bool] = []

    def cursor(self):
        self.autocommit_seen.append(self.autocommit)
        return Cur(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def sqls(self, prefix: str) -> list[str]:
        return [s for s, _p in self.log if s.startswith(prefix)]


class Http:
    def __init__(self, status=200):
        self.sent: dict = {}
        self.status = status

    def __call__(self, method, url, headers, body):
        self.sent[url.split("/published-assets/", 1)[1]] = body
        return self.status


# ── size verdict ─────────────────────────────────────────────────────────────────────────────────
def test_the_verdict_warns_at_70_percent_and_fails_at_85() -> None:
    q = flags.QUOTA_BYTES
    assert size.judge(int(q * 0.699))["status"] == size.OK
    assert size.judge(int(q * 0.70))["status"] == size.WARN
    assert size.judge(int(q * 0.849))["status"] == size.WARN
    assert size.judge(int(q * 0.85))["status"] == size.FAIL
    assert size.judge(q * 2)["share"] == 2.0
    assert flags.QUOTA_MB == 500 and flags.WARN_SHARE < flags.FAIL_SHARE < 1


def test_the_report_lists_top_tables_with_dead_ratio_and_tolerates_a_hidden_wal() -> None:
    conn = Conn(db_bytes=300 * 1048576, tables=[("live_events", 40 * 1048576, 30 * 1048576, 900, 100), ("pulses", 1000, 900, 0, 0)], wal=None)
    rep = size.report(conn)
    assert rep["status"] == size.OK and rep["share"] == 0.6 and rep["wal_bytes"] is None
    assert rep["tables"][0] == {"table": "live_events", "total_bytes": 40 * 1048576, "heap_bytes": 30 * 1048576, "live_rows": 900,
                                "dead_rows": 100, "dead_ratio": 0.1}
    assert rep["tables"][1]["dead_ratio"] == 0.0
    assert size.report(Conn(db_bytes=1, wal=16 * 1048576))["wal_bytes"] == 16 * 1048576
    assert "300.0 MB of 500.0 MB (60%)" in size.summary_line(rep) and "live_events" in size.summary_line(rep)


def test_storage_usage_is_judged_against_its_own_quota_by_prefix() -> None:
    mb = 1048576
    rep = size.report(Conn(db_bytes=10 * mb, storage=[("docs", 600 * mb), ("live", 150 * mb), ("analytics", 5 * mb)]))
    st = rep["storage"]
    assert st["by_prefix"] == {"docs": 600 * mb, "live": 150 * mb, "analytics": 5 * mb} and st["quota_bytes"] == flags.STORAGE_QUOTA_BYTES
    assert st["status"] == size.WARN and st["share"] == round(755 / 1024, 4)
    assert size.report(Conn(db_bytes=1))["storage"]["size_bytes"] == 0


def test_derived_caps_follow_from_the_quota_and_the_bucket() -> None:
    assert flags.ROW_CAP_BYTES == flags.QUOTA_BYTES // 1000
    sql = next(p for p in (Path(__file__).resolve().parents[1] / "migrations").glob("006_*.sql")).read_text(encoding="utf-8")
    assert f"{flags.STORAGE_OBJECT_BYTES}" in sql                       # the object cap IS the bucket's file_size_limit


# ── retention ────────────────────────────────────────────────────────────────────────────────────
def test_database_windows_agree_with_the_local_ones_that_also_prune() -> None:
    from algent_backend.live.memory import flags as live_memory
    from algent_backend.maritime import flags as maritime

    assert flags.LIVE_ANOMALIES_DAYS == live_memory.RETAIN_DAYS and flags.MARITIME_EVENTS_DAYS == maritime.RETAIN_DAYS


def test_rules_touch_only_growing_tables_and_never_the_corpus() -> None:
    tables = {r.table for r in prune.rules()}
    assert tables == {"live_events", "live_stats", "live_anomalies", "maritime_events", "radar_sightings", "published_article_revisions"}
    for corpus in ("published_articles", "pulses", "pulse_influences", "research_profiles", "geo_assets", "geo_asset_events", "sanctions_events",
                   "calendar_items", "events", "watches"):
        assert corpus not in tables


def test_selection_keeps_what_the_site_shows() -> None:
    by = {r.table: prune.delete_sql(r) for r in prune.rules()}
    assert "not active" in by["live_events"] and "ctid" in by["live_events"] and f"limit {flags.PRUNE_BATCH}" in by["live_events"]
    assert "not partial" in by["live_stats"] and "current_date" in by["live_stats"]       # the running day is never pruned
    assert "ended_at is not null" in by["maritime_events"] and "not active" in by["maritime_events"]
    assert "row_number() over (partition by slug order by id desc)" in by["published_article_revisions"]
    assert {r.table: r.arg for r in prune.rules()}["published_article_revisions"] == flags.REVISIONS_KEEP


def test_a_dry_run_counts_and_deletes_nothing() -> None:
    conn = Conn(remaining={"live_events": 123})
    out = prune.run(conn)
    assert out["applied"] is False and {p["table"]: p["rows"] for p in out["plan"]}["live_events"] == 123
    assert conn.sqls("delete") == [] and conn.sqls("vacuum") == []


def test_apply_deletes_in_batches_commits_each_and_vacuums_only_what_shrank() -> None:
    conn = Conn(remaining={"live_events": flags.PRUNE_BATCH * 2 + 5, "radar_sightings": 3})
    out = prune.run(conn, apply=True)
    deleted = {r["table"]: r["deleted"] for r in out["removed"]}
    assert deleted["live_events"] == flags.PRUNE_BATCH * 2 + 5 and deleted["radar_sightings"] == 3 and deleted["live_stats"] == 0
    assert len(conn.sqls("delete from live_events")) == 3                    # 2000, 2000, 5: the short batch ends the loop
    assert conn.commits >= 3 + 1                                             # one commit per batch
    assert sorted(out["vacuumed"]) == ["live_events", "radar_sightings"]
    assert conn.sqls("vacuum") == ["vacuum (analyze) live_events", "vacuum (analyze) radar_sightings"]
    assert conn.autocommit is False                                          # restored: VACUUM ran in autocommit, the rest did not


def test_vacuum_runs_in_autocommit() -> None:
    conn = Conn()
    prune.vacuum(conn, ["live_events"], full=True)
    assert conn.sqls("vacuum") == ["vacuum (full, analyze) live_events"] and conn.autocommit_seen[-1] is True


# ── the diet ─────────────────────────────────────────────────────────────────────────────────────
def test_the_diet_dry_run_reports_and_changes_nothing() -> None:
    conn = Conn(inline={"daily/g/2026-10-01.json": {"a": 1}, "record.json": {"b": 2}})
    out = diet.run(conn, apply=False, http=Http())
    assert out["applied"] is False and out["documents"]["inline_documents"] == 2 and out["documents"]["moved"] == 0
    assert not conn.moved and conn.sqls("update") == [] and conn.sqls("delete") == []


def test_the_diet_uploads_then_nulls_each_body_and_is_idempotent() -> None:
    inline = {"daily/g/2026-10-01.json": {"a": 1}, "record.json": {"b": [1, 2]}}
    conn, http = Conn(inline=inline), Http()
    out = diet.run(conn, apply=True, http=http)
    assert out["documents"]["moved"] == 2 and out["documents"]["left"] == []
    assert set(http.sent) == {"docs/daily/g/2026-10-01.json.gz", "docs/record.json.gz"}
    assert conn.moved["record.json"][0] == "docs/record.json.gz" and conn.moved["record.json"][2] == doc_store.pack("record.json", inline["record.json"]).sha256
    assert not conn.inline                                                    # nothing inline is left
    assert out["vacuumed"][0] == "published_intel_documents"
    again = diet.run(conn, apply=True, http=Http())
    assert again["documents"]["inline_documents"] == 0 and again["documents"]["moved"] == 0


def test_a_failed_upload_leaves_the_body_in_place() -> None:
    conn = Conn(inline={"record.json": {"b": 1}})
    out = diet.run(conn, apply=True, http=Http(status=500))
    assert out["documents"]["moved"] == 0 and len(out["documents"]["left"]) == 1 and "record.json" in conn.inline and not conn.moved


def test_the_diet_refuses_to_delete_without_storage(monkeypatch) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    conn = Conn(inline={"record.json": {"b": 1}})
    try:
        diet.run(conn, apply=True)
    except RuntimeError as exc:
        assert "Storage is not configured" in str(exc)
    else:
        raise AssertionError("must refuse")
    assert "record.json" in conn.inline


def test_vacuum_full_takes_the_smallest_bloated_tables_first_and_stops_when_one_would_not_fit() -> None:
    mb = 1048576
    tables = [("big", 300 * mb, 0, 10, 90), ("published_intel_documents", 20 * mb, 0, 50, 0), ("mid", 40 * mb, 0, 10, 5),
              ("tiny", mb, 0, 1, 9), ("clean", 90 * mb, 0, 1000, 1)]
    conn = Conn(db_bytes=450 * mb, tables=tables)
    assert [t["table"] for t in diet.vacuum_full_plan(conn)] == ["published_intel_documents", "mid", "big"]
    out = diet.vacuum_full(conn, apply=True)
    assert out["vacuumed_full"] == ["published_intel_documents", "mid"] and "big" in out["note"] and "would not fit" in out["note"]
    assert diet.vacuum_full(conn)["applied"] is False


# ── doctor ───────────────────────────────────────────────────────────────────────────────────────
def test_doctor_reports_the_budget_and_names_the_fix() -> None:
    from algent_backend.ops import doctor

    class P(doctor.Probes):
        def __init__(self, used):
            self.used = used

        def db_budget(self):
            return size.report(Conn(db_bytes=self.used, tables=[("published_intel_documents", self.used, 0, 1, 0)]))

    env = {"DATABASE_URL": "postgresql://x"}
    mb = 1048576
    ok = doctor.check_db_budget(env, P(200 * mb))["database budget"]
    warn = doctor.check_db_budget(env, P(360 * mb))["database budget"]
    fail = doctor.check_db_budget(env, P(430 * mb))["database budget"]
    assert (ok["status"], warn["status"], fail["status"]) == ("ok", "warn", "fail")
    assert "newsroom db prune" in fail["detail"] and "published_intel_documents" in fail["detail"]
    assert doctor.check_db_budget({}, P(1)) == {}

    class WithStorage(P):
        def db_budget(self):
            return size.report(Conn(db_bytes=mb, storage=[("docs", 750 * mb)]))

    got = doctor.check_db_budget(env, WithStorage(0))
    assert got["storage budget"]["status"] == "warn" and "docs/ 750.0 MB" in got["storage budget"]["detail"]

    class Broken(P):
        def db_budget(self):
            raise RuntimeError("could not connect to postgresql://u:pw-secret@h/db")

    got = doctor.check_db_budget(env, Broken(1))["database budget"]
    assert got["status"] == "warn" and "pw-secret" not in got["detail"]


# ── churn guards on the live writers ─────────────────────────────────────────────────────────────
def test_an_unchanged_live_event_is_not_rewritten() -> None:
    from algent_backend.live import publish

    assert "is distinct from" in publish._EVENT and "excluded.data" in publish._EVENT and "live_events.data" in publish._EVENT


def test_ongoing_maritime_events_are_resent_only_when_they_change_or_age() -> None:
    from algent_backend.maritime import publish, store
    from algent_backend.maritime.contracts import BehaviourEvent

    def ev(**kw):
        base = dict(id="mb-1", kind="ais_gap", mmsi=1, name="X", started_at="2026-10-17T08:00:00+00:00", last_seen="2026-10-17T11:30:00+00:00",
                    confidence=0.6, rationale="r", summary="s", evidence=[[1, 2.0, 3.0, 4.0, "n"]])
        return BehaviourEvent(**{**base, **kw})

    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ALGENT_MARITIME_STORE"] = tmp
        try:
            t0 = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
            store.upsert([ev()], t0.timestamp())
            first, _ = publish.pending(now=t0)
            assert [e.id for e in first] == ["mb-1"]
            store.save_published("m", {"mb-1": [publish.signature(first[0]), t0.isoformat(timespec="seconds")]})
            # the vessel is still dark: last heard, evidence and detail move every pass, the site-visible parts do not
            t1 = t0 + timedelta(minutes=5)
            store.upsert([ev(last_seen="2026-10-17T12:04:00+00:00", evidence=[[1, 2.0, 3.0, 4.0, "n"], [2, 2.1, 3.1, 4.0, "n"]], detail={"hours": 6.1})], t1.timestamp())
            assert publish.pending(now=t1)[0] == []
            store.upsert([ev(last_seen="2026-10-17T18:00:00+00:00", evidence=[[3, 2.2, 3.2, 4.0, "n"]])], (t0 + timedelta(hours=6, minutes=5)).timestamp())
            assert [e.id for e in publish.pending(now=t0 + timedelta(hours=6, minutes=5))[0]] == ["mb-1"]        # aged: the row is refreshed
            store.save_published("m", {"mb-1": [publish.signature(first[0]), (t0 + timedelta(hours=6, minutes=5)).isoformat(timespec="seconds")]})
            store.upsert([ev(state="ended", ended_at="2026-10-17T19:00:00+00:00")], (t0 + timedelta(hours=7)).timestamp())
            assert [e.id for e in publish.pending(now=t0 + timedelta(hours=7))[0]] == ["mb-1"]                   # a state change goes at once
        finally:
            os.environ.pop("ALGENT_MARITIME_STORE", None)


# ── the reader and the writer agree on where a document lives ───────────────────────────────────
def test_the_site_reader_resolves_the_storage_key_the_writer_uses() -> None:
    ts = (Path(__file__).resolve().parents[2] / "sites" / "ohmega-monster" / "lib" / "store.ts").read_text(encoding="utf-8")
    assert "/docs/${rel}.gz" in ts and "gunzipSync" in ts and "DataUnavailable" in ts and "NEXT_PUBLIC_SUPABASE" not in ts
    assert doc_store.object_key("daily/geopolitics/2026-10-01.json") == "docs/daily/geopolitics/2026-10-01.json.gz"
