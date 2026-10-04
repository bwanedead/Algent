"""Migrations: discovered in order, run once, never out of order. No database needed."""

from __future__ import annotations

import pytest

from algent_backend.database import available, pending


def test_the_repo_ships_ordered_migrations() -> None:
    names = [p.stem for p in available()]
    assert names[:2] == ["001_pulse", "002_research_profiles"]
    assert names == sorted(names)


def test_pending_skips_what_ran_and_refuses_a_gap(tmp_path) -> None:
    for n in ("001_a", "002_b", "003_c"):
        (tmp_path / f"{n}.sql").write_text("select 1;", encoding="utf-8")
    assert [p.stem for p in pending(set(), tmp_path)] == ["001_a", "002_b", "003_c"]
    assert [p.stem for p in pending({"001_a"}, tmp_path)] == ["002_b", "003_c"]
    with pytest.raises(RuntimeError):
        pending({"001_a", "003_c"}, tmp_path)          # 003 ran but 002 never did


def test_the_ledger_is_append_only_in_the_schema_itself() -> None:
    sql = (available()[0]).read_text(encoding="utf-8")
    assert "before update or delete on pulse_influences" in sql
    assert "key                  text primary key" in sql      # idempotency at the lowest level
    assert sql.count("enable row level security") >= 9           # nothing public by accident
