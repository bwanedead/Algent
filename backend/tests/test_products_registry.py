"""The product registry: a product exists only if it is in ``ops/products/registry.py``, and everything operational is derived from it - the backup, the
envelope budgets, the systemd timers, the paid jobs, the docs table and the site contract. These tests fail when the code and the registry disagree.
Offline."""

from __future__ import annotations

import dataclasses
import json
import re
import time
from pathlib import Path

import pytest

from algent_backend.ops import flags as ops_flags, housekeeping, schedule
from algent_backend.ops.products import run as products_run, validate, views
from algent_backend.ops.products.model import Budget, Product, Retention
from algent_backend.ops.products.registry import PRODUCTS
from tests.jobq_fakes import queue

REPO = Path(__file__).resolve().parents[2]
INFRA = REPO / "infra" / "server"
SITE = REPO / "sites" / "ohmega-monster"


# ── the registry obeys its own rules ─────────────────────────────────────────────────────────────
def test_the_registry_is_a_coherent_set_of_products() -> None:
    assert validate.validate() == []


def test_every_store_resolves_to_a_path_and_follows_its_variable(monkeypatch, tmp_path) -> None:
    for _p, s in views.stores():
        if s.env:
            monkeypatch.setenv(s.env, str(tmp_path / s.env))
    for _p, s in views.stores():
        assert isinstance(s.path(), Path) and s.path().is_absolute()
        if s.env:
            assert str(s.path()).startswith(str(tmp_path / s.env)), f"{s.name} ignores {s.env}"


def _one(pid: str, **change) -> Product:
    return dataclasses.replace(views.by_id(pid), **change)


def _problems(p: Product) -> list[str]:
    return validate._product_problems(p, {j.name for _, j in views.jobs()})



def test_a_product_with_data_and_no_retention_policy_fails() -> None:
    assert any("no retention policy" in m for m in _problems(_one("sanctions", retention=())))


def test_unbounded_append_only_growth_fails_the_runway_rule() -> None:
    sanctions = views.by_id("sanctions")
    fast = dataclasses.replace(sanctions.stores[0], budget=Budget(7, 100, 500, 100, 50, "growing 50 MB a week would hit the fail line in 10 weeks"))
    assert any("fail line" in m for m in _problems(dataclasses.replace(sanctions, stores=(fast,))))


def test_a_prune_nothing_triggers_is_not_a_policy() -> None:
    bad = Retention("prune", "deletes old things", "ops/housekeeping.py::run", "job:no-such-job")
    assert any("no such job" in m for m in _problems(_one("ops", retention=(bad,))))
    assert any("reference the code" in m for m in _problems(_one("ops", retention=(Retention("prune", "x", "", "manual"),))))
    assert any("no such file" in m for m in _problems(_one("ops", retention=(Retention("prune", "x", "nope/missing.py::f", "manual"),))))


def test_the_irreplaceable_verdict_must_match_the_backup() -> None:
    assert any("irreplaceable" in m for m in _problems(_one("pulses", irreplaceable=False)))
    disposable = dataclasses.replace(views.by_id("library").stores[0], backed_up=True)
    assert any("irreplaceable" in m for m in _problems(_one("library", stores=(disposable,))))
    silent = dataclasses.replace(views.by_id("library").stores[0], why_not="")
    assert any("gives no reason" in m for m in _problems(_one("library", stores=(silent,))))


def test_every_store_has_a_budget_and_every_job_a_cadence() -> None:
    assert all(s.budget for _, s in views.stores())
    assert all(j.every_min > 0 for _, j in views.timers())
    no_job = _one("sanctions", jobs=(), manual="")
    assert any("no job and no `manual`" in m for m in _problems(no_job))


def test_names_are_unique_and_feeds_from_has_no_cycle() -> None:
    assert len({p.id for p in PRODUCTS}) == len(PRODUCTS)
    a = dataclasses.replace(views.by_id("pulses"), feeds_from=("situations",))      # situations already feeds_from pulses
    cycle = [a if p.id == "pulses" else p for p in PRODUCTS]
    original = validate.views.products
    validate.views.products = lambda: tuple(cycle)
    try:
        assert any("cycle" in m for m in validate._cycles())
    finally:
        validate.views.products = original


# ── backups: derived ─────────────────────────────────────────────────────────────────────────────
def test_the_backup_is_the_irreplaceable_products_and_the_rest_say_why() -> None:
    covered = set(views.backup_sources())
    assert {"pulse_store", "profile_store", "intel_store", "site_intel", "draft_store"} <= covered
    for name, why in views.excluded_stores().items():
        assert name not in covered and len(why) > 20


# ── timers: derived, and the shell scripts hold none of their own ────────────────────────────────
def test_the_installer_reads_its_timers_from_the_registry() -> None:
    text = (INFRA / "install_schedules.sh").read_text(encoding="utf-8")
    assert "newsroom products timers" in text
    assert not re.search(r"^unit \S+ +\"", text, flags=re.M), "a hand-written timer line is back in install_schedules.sh"
    for _p, j in views.jobs():
        if j.kind == "service":
            assert f"ohmega-{j.name}.service" in text and f"enable --now ohmega-{j.name}.service" in text, f"service {j.name} is registered but not installed"


def test_jobs_sh_is_a_one_line_router_to_the_registry() -> None:
    text = (INFRA / "jobs.sh").read_text(encoding="utf-8")
    assert "products run" in text and "case " not in text and "flock" not in text


def test_timer_lines_are_name_command_calendar_and_cover_every_timer() -> None:
    rows = [line.split("\t") for line in views.timer_lines()]
    assert all(len(r) == 3 and r[2] for r in rows)
    assert {r[0] for r in rows} == {j.name for _, j in views.timers()}
    assert "jobs.sh library" in [r[1] for r in rows] and ["update", "update.sh", "*:0/5"] in rows
    assert (INFRA / "update.sh").is_file()
    live = {r[0]: r[2] for r in rows if r[0].startswith("live-")}
    assert live["live-ioda"] == "*:0/15" and live["live-firms"] == "*-*-* 0/3:00:00"


def test_every_scheduled_time_is_still_the_one_the_server_had() -> None:
    """The refactor must not move a timer: these are the calendars install_schedules.sh carried by hand before the registry."""
    got = {r.split("\t")[0]: r.split("\t")[2] for r in views.timer_lines()}
    assert {
        "library": "0/4:20", "instruments": "0/6:40", "statements": "1/6:10", "sanctions": "2/6:25", "calendar": "*-*-* 04:40", "markets": "3/4:50",
        "ai-bench": "0/12:55", "ai-discovery": "*-*-* 06:50", "backup": "*-*-* 06:15", "backup-snapshot": "*-*-* 06:40", "backup-drill": "*-*-01 07:30:00",
        "envelope": "*-*-* 07:10", "db-prune": "*-*-* 03:40", "maritime-rollup": "*-*-* 04:05", "watchdog": "*:0/2", "flows": "*:7/15",
        "satellite": "*-*-* 03:20", "menu": "*-*-* 05:00:00", "daily-1": "*-*-* 05:30:00", "daily-2": "*-*-* 17:30:00", "markets-daily": "*-*-* 07:30:00",
    }.items() <= got.items()


def test_jobs_that_must_not_wait_skip_the_lock() -> None:
    for name in ("watchdog", "flows", "satellite", "live-ioda", "update"):
        assert not views.job(name)[1].lock, f"{name} must not queue behind a daily"
    assert views.job("library")[1].lock and views.job("daily-1")[1].lock


def test_the_watchdog_never_times_the_job_router() -> None:
    assert "products" in ops_flags.FREE_COMMANDS


# ── paid jobs: derived ───────────────────────────────────────────────────────────────────────────
def test_the_paid_jobs_are_the_registry_jobs_marked_paid() -> None:
    paid = schedule.jobs()
    assert set(paid) == {j.name for _, j in views.paid_jobs()} >= {"menu", "daily-1", "daily-2", "markets-daily"}
    assert paid["menu"].argv == ("run", "--to", "menu") and paid["menu"].utc == ops_flags.MENU_UTC
    assert paid["daily-2"].argv[-2:] == ("--edition", "2") and paid["markets-daily"].argv == ("markets", "daily")
    assert all(j.spend == "paid" and j.hhmm() for _, j in views.paid_jobs())


def test_the_ai_daily_follows_its_switch(monkeypatch) -> None:
    from algent_backend.agent_system.agents.intel import flags

    monkeypatch.setattr(flags, "AI_DAILY_SCHEDULED", False)
    assert "ai-daily" not in schedule.jobs()
    monkeypatch.setattr(flags, "AI_DAILY_SCHEDULED", True)
    assert "ai-daily" in schedule.jobs()


# ── run: the router ──────────────────────────────────────────────────────────────────────────────
def test_run_unknown_and_service_jobs_are_refused(capsys) -> None:
    assert products_run.run_job("no-such-job") == 2
    assert products_run.run_job("ais") == 2


def test_run_takes_the_lock_only_when_the_job_asks_and_runs_its_command(monkeypatch, tmp_path) -> None:
    calls, locked = [], []
    q, env, _ledger = queue(tmp_path)
    real = env.try_lock
    env.try_lock = lambda: locked.append("taken") or real()                    # type: ignore[method-assign]
    monkeypatch.setattr(products_run, "make_queue", lambda: q)
    monkeypatch.setattr(products_run.measure, "call", lambda cmd, cwd=None: calls.append(cmd) or 0)
    assert products_run.run_job("library") == 0
    assert calls[-1][-4:] == ["library", "crawl", "--max", "150"] and locked == ["taken"] and not env.mine
    locked.clear()
    assert products_run.run_job("watchdog") == 0 and locked == [] and calls[-1][-1] == "watchdog"


def test_run_sends_a_paid_job_through_the_spend_gates(monkeypatch, tmp_path) -> None:
    seen = []
    monkeypatch.setattr(products_run, "make_queue", lambda: queue(tmp_path)[0])
    monkeypatch.setattr(schedule, "run_job", lambda name, **k: seen.append(name) or 0)
    monkeypatch.setattr(products_run.measure, "call", lambda *a, **k: pytest.fail("a paid job must not bypass ops/schedule.py"))
    assert products_run.run_job("menu") == 0 and seen == ["menu"]


# ── retention entry points ───────────────────────────────────────────────────────────────────────
def test_every_prune_and_rollup_names_a_registered_job_or_its_writer() -> None:
    kinds = [(p.id, r) for p in PRODUCTS for r in p.retention if r.kind in ("prune", "rollup")]
    assert kinds
    names = {j.name for _, j in views.jobs()}
    for pid, r in kinds:
        assert r.by == "on-write" or r.by.removeprefix("job:") in names, f"{pid}: {r.by}"


def test_housekeeping_expires_the_fetch_cache_and_old_run_logs(tmp_path, monkeypatch) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    old, new = cache / "old.json", cache / "new.json"
    old.write_text("{}", encoding="utf-8")
    new.write_text("{}", encoding="utf-8")
    import os

    stale = time.time() - 7 * 3600
    os.utime(old, (stale, stale))
    logs = tmp_path / "runlogs"
    logs.mkdir()
    (logs / "menu-2026-01-01.log").write_text("x", encoding="utf-8")
    (logs / "menu-today.log").write_text("x", encoding="utf-8")
    ancient = time.time() - 40 * 86400
    os.utime(logs / "menu-2026-01-01.log", (ancient, ancient))
    monkeypatch.setenv("ALGENT_FETCH_CACHE_DIR", str(cache))
    dry = housekeeping.run(apply=False, home=tmp_path)
    assert dry["fetch_cache"]["expired"] == 1 and dry["runlogs"]["expired"] == 1 and old.exists()
    done = housekeeping.run(apply=True, home=tmp_path)
    assert done["fetch_cache"]["deleted"] == 1 and done["runlogs"]["deleted"] == 1
    assert not old.exists() and new.exists() and (logs / "menu-today.log").exists()


# ── docs table: generated, and the doc matches ───────────────────────────────────────────────────
def test_the_foundation_doc_embeds_the_current_table() -> None:
    doc = (REPO / "docs" / "architecture" / "foundation.md").read_text(encoding="utf-8")
    assert views.TABLE_START in doc and views.TABLE_END in doc
    assert views.embed(doc.replace("\r\n", "\n")) == doc.replace("\r\n", "\n"), "foundation.md section 3 is stale: run `newsroom products table --write`"
    assert all(f"`{p.id}`" in doc for p in PRODUCTS)


# ── the site contract ────────────────────────────────────────────────────────────────────────────
def _page_routes() -> set[str]:
    out = set()
    for page in (SITE / "app").rglob("page.tsx"):
        parts = [x for x in page.relative_to(SITE / "app").parent.parts if not (x.startswith("(") and x.endswith(")"))]
        out.add("/" + "/".join(parts))
    return out


def _sitemap_routes() -> set[str]:
    text = (SITE / "app" / "sitemap.ts").read_text(encoding="utf-8")
    return {re.sub(r"\$\{[^}]+\}", "[x]", m).rstrip("/") or "/" for m in re.findall(r"`\$\{SITE_URL\}(/[^`]*)`", text)}


def _doc_routes() -> set[str]:
    text = (REPO / "docs" / "architecture" / "information-architecture.md").read_text(encoding="utf-8")
    section = text.split("## 3. Navigation")[1].split("## 4.")[0]
    out = set()
    for row in section.splitlines():
        if row.startswith("| `/"):
            for route in re.findall(r"`(/[^`]*)`", row.split("|")[1]):
                out.add(re.sub(r"<[^>]+>", "[x]", route))
    return out


def test_every_page_route_belongs_to_a_product() -> None:
    pages = _page_routes()
    assert "/" in pages and "/daily/[desk]/[date]" in pages
    orphans = sorted(r for r in pages if views.owner_of_route(r) is None)
    assert not orphans, f"page(s) {orphans} are read by no product: add the route to the owning product's site_routes"


def test_every_sitemap_and_ia_route_belongs_to_a_product() -> None:
    for what, routes in (("sitemap.ts", _sitemap_routes()), ("information-architecture.md", _doc_routes())):
        assert routes, what
        orphans = sorted(r for r in routes if views.owner_of_route(r) is None)
        assert not orphans, f"{what} lists route(s) {orphans} that no product owns"


def test_every_registered_route_is_a_real_page_or_redirect() -> None:
    pages = _page_routes()
    for p in PRODUCTS:
        for r in p.site_routes:
            assert r in pages, f"{p.id} lists {r}, which is not a page under sites/ohmega-monster/app"


def test_the_site_contract_file_is_the_generated_one() -> None:
    on_disk = json.loads((SITE / "lib" / "products.json").read_text(encoding="utf-8"))
    assert on_disk == views.site_contract(), "sites/ohmega-monster/lib/products.json is stale: run `newsroom products contract --write`"
    assert on_disk["schema"] == "ohmega.products/1" and {p["id"] for p in on_disk["products"]} == {p.id for p in PRODUCTS}


def test_route_matching_handles_dynamic_segments() -> None:
    assert views.owner_of_route("/daily/ai/2026-10-23") == "dailies"
    assert views.owner_of_route("/daily/headlines") == "menu"
    assert views.owner_of_route("/situations/thr_x") == "situations"
    assert views.owner_of_route("/") == "site"
    assert views.owner_of_route("/nope/at/all") is None
