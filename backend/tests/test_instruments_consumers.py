"""evidence_block / moves_board formatting, catalog integrity, collector isolation, CLI smoke."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from algent_backend.cli import __main__ as cli
from algent_backend.instruments import collect as collect_mod
from algent_backend.instruments import evidence_block, moves_board, store
from algent_backend.instruments.catalog import CATALOG, get_series, match
from algent_backend.instruments.contracts import Observation
from algent_backend.instruments.http import SourceError, SourceUnavailable
from algent_backend.instruments.sources import PROVIDERS


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_INSTRUMENTS_STORE", str(tmp_path / "istore"))


def mk(sid, period, value):
    return Observation(series_id=sid, period=period, value=value, fetched_at="t", source_url="u")


def seed_hormuz():
    sid, today = "chk_hormuz_transits", date.today()
    obs = [mk(sid, (today - timedelta(days=i)).isoformat(), 100.0 + (i % 7)) for i in range(300, 5, -1)]
    obs += [mk(sid, (today - timedelta(days=i)).isoformat(), 2.0) for i in range(5, 0, -1)]
    store.append(sid, obs)


def test_catalog_ids_unique_providers_registered_and_tags_lowercase():
    assert len({s.id for s in CATALOG}) == len(CATALOG)
    assert all(s.fetcher in PROVIDERS for s in CATALOG)
    assert all(t == t.lower() for s in CATALOG for t in s.tags)
    assert all(not s.public_display for s in CATALOG if s.fetcher == "yahoo")
    assert {"chk_hormuz_transits", "chk_hormuz_tanker_transits"} <= {s.id for s in match(["hormuz"])}


def test_evidence_block_format():
    seed_hormuz()
    lines = evidence_block(["hormuz"]).splitlines()
    assert lines[0].startswith("INSTRUMENTS") and len(lines) == 2          # only stored series appear
    line = lines[1]
    assert "[chk_hormuz_transits]" in line and "2 ships/day" in line and "UNUSUAL" in line
    assert "at 90d low" in line and "source: IMF PortWatch https://portwatch.imf.org/" in line
    assert "vs prev" in line and "1y percentile" in line


def test_evidence_block_empty_when_nothing_matches_or_stored():
    assert evidence_block(["hormuz"]) == ""
    seed_hormuz()
    assert evidence_block(["nonexistent-tag"]) == ""


def test_evidence_block_as_of_replays_before_collapse():
    seed_hormuz()
    assert "UNUSUAL" not in evidence_block(["hormuz"], as_of=date.today() - timedelta(days=10))


def test_moves_board_puts_unusual_first_and_marks_internal():
    seed_hormuz()
    store.append("px_brent", [mk("px_brent", "2026-10-01", 90.0)])
    board = moves_board(["energy"])
    assert board[0]["series_id"] == "chk_hormuz_transits" and board[0]["unusual"]
    assert "[internal source]" in evidence_block(["brent"], as_of=date(2026, 10, 4))


def test_collector_isolates_failures(monkeypatch):
    def blocked(s, since): raise SourceUnavailable("needs key")
    def down(s, since): raise SourceError("http://x failed")
    def boom(s, since): raise ValueError("odd shape")
    monkeypatch.setitem(PROVIDERS, "portwatch", lambda s, since: [mk(s.id, "2026-10-01", 1.0)])
    monkeypatch.setitem(PROVIDERS, "agsi", blocked)
    monkeypatch.setitem(PROVIDERS, "yahoo", down)
    monkeypatch.setitem(PROVIDERS, "ecb", boom)
    ids = ["chk_hormuz_transits", "gas_eu_storage", "px_brent", "px_wti", "fx_eurusd_ecb"]
    rep = collect_mod.collect(ids, today=date(2026, 10, 4))
    assert {r["id"]: r["status"] for r in rep["series"]} == {
        "chk_hormuz_transits": "ok", "gas_eu_storage": "blocked", "px_brent": "error",
        "px_wti": "skipped", "fx_eurusd_ecb": "error"}
    assert store.history("chk_hormuz_transits")[0].value == 1.0


def test_collect_window_uses_overlap_then_backfill():
    s = get_series("chk_hormuz_transits")
    assert collect_mod._since(s, False, date(2026, 10, 4)) is None
    seed_hormuz()
    latest = date.today() - timedelta(days=1)
    assert collect_mod._since(s, False, date.today()) == latest - timedelta(days=collect_mod.OVERLAP_DAYS)
    assert collect_mod._since(s, True, date(2026, 10, 4)) == date(2026, 10, 4) - timedelta(days=collect_mod.BACKFILL_DAYS)


def run_cli(capsys, *argv):
    assert cli.main(["newsroom", "instruments", *argv]) == 0
    return json.loads(capsys.readouterr().out)


def test_cli_show_and_moves(capsys):
    seed_hormuz()
    row = next(r for r in run_cli(capsys, "show")["series"] if r["id"] == "chk_hormuz_transits")
    assert row["n_obs"] == 300
    one = run_cli(capsys, "show", "--series", "chk_hormuz_transits", "--last", "3")
    assert len(one["observations"]) == 3 and one["n_obs"] == 300
    mv = run_cli(capsys, "moves", "--tag", "hormuz")
    assert mv["count"] == 1 and mv["unusual"] == ["chk_hormuz_transits"]


def test_cli_fetch_uses_collector(capsys, monkeypatch):
    monkeypatch.setitem(PROVIDERS, "portwatch", lambda s, since: [mk(s.id, "2026-10-01", 7.0)])
    rep = run_cli(capsys, "fetch", "--series", "chk_hormuz_transits")
    assert rep["ok"] == 1 and rep["series"][0]["new"] == 1
