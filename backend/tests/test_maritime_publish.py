"""Maritime publish shape (migration 013, watermark, idempotence), the geoledger link, the desk block, the CLI and the stream hook. Offline."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from algent_backend.maritime import desk, publish, store
from algent_backend.maritime.contracts import BehaviourEvent

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_MARITIME_STORE", str(tmp_path / "maritime"))
    monkeypatch.setenv("ALGENT_LIVE_STORE", str(tmp_path / "live"))
    monkeypatch.delenv("DATABASE_URL", raising=False)


def ev(kind="sanctioned", mmsi=636092000, conf=0.95, **kw) -> BehaviourEvent:
    base = dict(id=f"mb-{kind}-{mmsi}", kind=kind, mmsi=mmsi, name="NORDIC STAR", imo="9074729", flag="LR", ship_class="tanker",
                started_at="2026-10-17T08:00:00+00:00", last_seen="2026-10-17T11:30:00+00:00", lat=26.4, lon=56.4, area="Strait of Hormuz",
                countries=["Iran", "Oman", "United Arab Emirates"], confidence=conf, rationale="because", summary="NORDIC STAR was seen in Hormuz",
                detail={"asset_id": "og-xx-vessel-imo9074729", "basis": "imo"}, evidence=[[1, 26.4, 56.4, 3.0, "x"]])
    return BehaviourEvent(**{**base, **kw})


class Cur:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def executemany(self, sql, rows):
        self.log.extend((sql, r) for r in rows)


class Conn(Cur):
    def __init__(self):
        self.log = []

    def cursor(self):
        return Cur(self.log)

    def commit(self):
        pass


def test_the_migration_is_public_read_only_and_carries_every_published_column():
    from algent_backend.database import available

    sql = next(p for p in available() if p.stem == "013_maritime_events").read_text(encoding="utf-8")
    assert "create table maritime_events" in sql and "enable row level security" in sql and "for select to anon" in sql
    assert "revoke insert, update, delete, truncate on maritime_events from anon, authenticated" in sql
    for col in publish._COLUMNS:
        assert col in sql, col
    assert [p.stem for p in available()] == sorted(p.stem for p in available())


def test_publish_upserts_changed_events_prunes_and_is_idempotent():
    store.upsert([ev(), ev("ais_gap", 538000001, 0.6, state="ended", ended_at="2026-10-17T10:00:00+00:00")], NOW.timestamp())
    conn = Conn()
    res = publish.publish(connect=lambda: conn)
    assert res == {"db": True, "events": 2}
    inserts = [p for s, p in conn.log if s.strip().startswith("insert into maritime_events")]
    assert {r[0] for r in inserts} == {"mb-sanctioned-636092000", "mb-ais_gap-538000001"}
    row = next(r for r in inserts if r[0] == "mb-sanctioned-636092000")
    cols = publish._COLUMNS
    assert row[cols.index("active")] is True and row[cols.index("provenance")] == "ohmega_derived" and json.loads(row[cols.index("evidence")])[0][0] == 1
    assert json.loads(row[cols.index("detail")])["basis"] == "imo"
    assert any(s.startswith("delete from maritime_events") for s, _p in conn.log)
    again = Conn()
    assert publish.publish(connect=lambda: again) == {"db": True, "events": 0, "note": "nothing new"} and again.log == []
    store.upsert([ev(conf=0.99)], NOW.timestamp() + 600)                              # one changes: only it is sent
    third = Conn()
    assert publish.publish(connect=lambda: third)["events"] == 1
    assert publish.publish(full=True, connect=lambda: Conn())["events"] == 2


def test_a_failed_publish_keeps_the_watermark_so_it_retries_whole():
    store.upsert([ev()], NOW.timestamp())

    def broken():
        raise RuntimeError("db down")

    assert publish.publish(connect=broken)["db"] is False and store.published_at() == ""
    assert publish.publish(connect=lambda: Conn())["events"] == 1
    assert publish.publish()["note"] == "nothing new"                                  # no DATABASE_URL and nothing new


def test_without_a_database_publish_is_a_noop_but_never_raises():
    store.upsert([ev()], NOW.timestamp())
    assert publish.publish()["db"] is False


def test_events_on_a_vessel_the_ledger_knows_become_behaviour_flagged_status_events(tmp_path):
    from algent_backend.geoledger import contracts as gc
    from algent_backend.geoledger.store import Ledger

    ledger = Ledger(tmp_path / "geo")
    ledger.add_assets([gc.Asset(id="og-xx-vessel-imo9074729", name="NORDIC STAR", type="vessel", country="LR", precision="unplaced")])
    ledger.add_events([gc.StatusEvent(id="ev-des", asset_id="og-xx-vessel-imo9074729", occurred_on="2026-09-01", status="designated",
                                      claimant="US Treasury OFAC")])
    gap = ev("ais_gap", conf=0.6, detail={})                                            # no asset_id in detail: found by IMO
    stranger = ev("sts", 538000009, 0.7, imo="9999995", detail={})                       # an IMO the ledger does not know
    out = publish.link_ledger([ev(), gap, stranger], ledger)
    assert out == {"events": 2, "skipped": 0}                                            # the stranger's IMO has no asset: nothing is minted
    flagged = [e for e in ledger.history("og-xx-vessel-imo9074729") if e.status == "behaviour_flagged"]
    assert len(flagged) == 1 and flagged[0].claimant == "Ohmega analysis" and flagged[0].provenance == "ohmega_derived"
    assert flagged[0].occurred_on == "2026-10-17" and flagged[0].confidence == "high" and flagged[0].via.startswith("maritime:")
    assert ledger.status("og-xx-vessel-imo9074729").status == "designated"             # a behaviour flag never replaces the asset's own state
    assert publish.link_ledger([ev()], ledger)["events"] == 1 and len(ledger.history("og-xx-vessel-imo9074729")) == 2   # idempotent


def test_the_desk_block_shows_events_in_areas_touching_the_theaters_countries_with_their_reason():
    store.upsert([ev(), ev("loiter", 538000002, 0.4, area="Gulf of Finland cable and pipeline corridor (proxy)", countries=["Finland", "Estonia"],
                           summary="X loitered 5.0 h"), ev("identity", 538000003, 0.3, area="", countries=[], summary="Y renamed"),
                  ev("ais_gap", 538000004, 0.8, state="ended", ended_at="2026-09-01T00:00:00+00:00", last_seen="2026-09-01T00:00:00+00:00")],
                 NOW.timestamp())
    text, urls, n = desk.block({"Iran"}, NOW)
    assert n == 1 and text.startswith("OHMEGA MARITIME") and "Why flagged: because" in text and "confidence 95%" in text and urls == {desk.PAGE_URL}
    assert "loitered" not in text and "renamed" not in text and "ended" not in text.split("\n", 1)[1]
    assert desk.block({"Chad"}, NOW) == ("", set(), 0)
    sweep, _u, k = desk.block_all(NOW)
    assert k == 3 and "Y renamed" in sweep and sweep.index("NORDIC STAR") < sweep.index("X loitered")      # strongest first; the old one is gone

    def corroborate(find):
        return find("Iran and Oman talks near Hormuz")

    text2, _u2, n2 = desk.for_theater(corroborate, lambda t, names: {c for c in names if c in t})
    assert n2 == 1 and "NORDIC STAR" in text2


def test_the_evidence_block_renders_between_anomalies_and_the_rest():
    from algent_backend.agent_system.agents.intel.sensing import Evidence

    e = Evidence(anomalies="A", maritime="M", statements="S")
    assert e.render().index("A") < e.render().index("M") < e.render().index("S")


def test_the_cli_reads_what_the_stream_wrote(capsys):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[1] / "algent_backend" / "cli" / "newsroom" / "maritime.py"     # loaded alone: the package imports every command
    spec = importlib.util.spec_from_file_location("maritime_cli", path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    store.upsert([ev(), ev("ais_gap", 538000001, 0.2)], NOW.timestamp())

    class A:
        kind, min_confidence, limit = None, 0.5, 10

    assert cli.run_events(A()) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["count"] == 1 and out["events"][0]["kind"] == "sanctioned"
    assert cli.run_status(A()) == 0 and json.loads(capsys.readouterr().out)["events"]["sanctioned"] == {"total": 1, "active": 1}


def test_the_stream_hook_never_raises_and_the_runner_publishes_after_memory(monkeypatch):
    from algent_backend.live import runner, stream

    class Boom:
        def cycle(self, *_a):
            raise RuntimeError("x")

    assert stream._watch_cycle(Boom(), object(), 0.0) is None
    assert runner.store.read_status()["maritime"]["error"].startswith("RuntimeError")
    store.upsert([ev()], NOW.timestamp())
    seen = []
    monkeypatch.setattr(publish, "run", lambda connect=None: seen.append(1) or {"ok": True})
    monkeypatch.setattr(runner, "FEEDS", {})
    monkeypatch.setattr(runner, "TIMER_FEEDS", ())
    from algent_backend.live.memory import tick

    monkeypatch.setattr(tick, "tick", lambda *a, **k: {})
    out = runner.run([], get=lambda *a, **k: "", now=NOW, publish=True)
    assert seen == [1] and out["maritime"] == {"ok": True}
