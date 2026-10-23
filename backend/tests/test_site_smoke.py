"""The post-deploy smoke test (ops/smoke): probes derived from the registry and the sitemap, every check rule, the report, the state and the CLI. Offline: a fake site."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from algent_backend.cli.newsroom import site as cli
from algent_backend.ops import smoke  # noqa: F401 - the package imports
from algent_backend.ops.smoke import checks, flags, probes, run, state
from algent_backend.ops.smoke.fetch import Reply

BASE = "https://preview.example"
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
HTML = "<html><head><title>Ohmega</title></head><body><main>fine page</main><script>{\"a\":\"has not been published\"}</script></body></html>"

SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://ohmega.monster/daily/geopolitics/2026-10-21</loc></url>
<url><loc>https://ohmega.monster/daily/geopolitics/2026-10-23</loc></url>
<url><loc>https://ohmega.monster/daily/ai/2026-10-22</loc></url>
<url><loc>https://ohmega.monster/situations/hormuz</loc></url><url><loc>https://ohmega.monster/situations/other</loc></url>
<url><loc>https://ohmega.monster/intel/actors/IR</loc></url><url><loc>https://ohmega.monster/articles/hello</loc></url>
<url><loc>https://ohmega.monster/intel/places/p1</loc></url><url><loc>https://ohmega.monster/intel/briefs/b1</loc></url>
</urlset>"""


def envelope(data=None, as_of="2026-10-23", **meta):
    m = {"as_of": as_of, "source": "ohmega.x/1", "version": "v1", "cite_as": "https://ohmega.monster", "license": "l", **meta}
    return json.dumps({"data": {"k": 1} if data is None else data, "meta": m}).encode()


class FakeSite:
    """A healthy site by default; ``overrides`` maps a path to a Reply (or a callable) to break one thing."""

    def __init__(self, **overrides) -> None:
        self.overrides, self.asked = overrides, []

    def __call__(self, url: str) -> Reply:
        path = url[len(BASE):]
        self.asked.append(path)
        if path in self.overrides:
            o = self.overrides[path]
            return o() if callable(o) else o
        if path == "/sitemap.xml":
            return Reply(200, body=SITEMAP.encode(), ms=50)
        if path == "/robots.txt":
            return Reply(200, body=b"User-agent: *\nSitemap: https://ohmega.monster/sitemap.xml", ms=20)
        if path == "/feed.xml":
            return Reply(200, body=b"<rss><channel/></rss>", ms=20)
        if path == "/llms-full.txt":
            return Reply(200, body=b"x" * 100, ms=20)
        for src, dest in flags.REDIRECTS:
            if path == src:
                return Reply(308, {"location": dest}, ms=10)
        if path.startswith("/api/v1/openapi.json") or path.startswith("/api/globe/"):
            return Reply(200, body=b'{"openapi":"3.0.0"}', ms=30)
        if path.startswith("/api/v1"):
            return Reply(200, body=envelope(), ms=80)
        return Reply(200, body=HTML.encode(), ms=120)


def smoke(site, **kw):
    return run.run(BASE, fetch=site, now=NOW, pace=0, sleep=lambda _s: None, **kw)


def by_path(report, path):
    return next(r for r in report.results if r.path == path)


def test_a_healthy_site_passes_and_covers_the_registry_the_samples_and_the_api() -> None:
    site = FakeSite()
    rep = smoke(site)
    assert rep.ok and rep.count("fail") == 0, rep.text()
    asked = set(site.asked)
    assert {"/", "/daily", "/situations", "/data", "/live", "/intel/forecasts", "/sitemap.xml", "/api/v1", "/api/v1/series?metric=gdp"} <= asked   # registry + API
    assert {"/daily/geopolitics/2026-10-23", "/daily/ai/2026-10-22", "/situations/hormuz", "/intel/actors/IR", "/articles/hello"} <= asked         # samples
    assert "/daily/geopolitics/2026-10-21" not in asked and "/situations/other" not in asked        # the newest per desk, one per template
    assert "/api/globe/country/IR" in asked and "/daily/ai/archive" in asked                          # derived from a sample / filled from the desks
    assert {"/api/v1/daily/geopolitics/latest", "/api/v1/daily/ai/latest"} <= asked
    assert "/geopolitics" in asked and by_path(rep, "/geopolitics").kind == "redirect"
    assert all(r.ms >= 0 for r in rep.results) and rep.p95_ms() > 0 and rep.text().startswith("smoke https://preview.example - OK")


def test_every_registered_static_route_is_probed() -> None:
    paths = {p.path for p in probes.static_probes()}
    from algent_backend.ops.products import views

    for p in views.products():
        for route in p.site_routes:
            if "[" not in route:
                assert route in paths, route


def test_a_missing_page_fails_by_status() -> None:
    rep = smoke(FakeSite(**{"/pulses": Reply(404, body=b"nope", ms=10)}))
    assert not rep.ok and by_path(rep, "/pulses").severity == "fail" and "status 404" in by_path(rep, "/pulses").notes[0]


def test_not_published_copy_on_a_page_fails_but_a_script_payload_does_not() -> None:
    page = "<html><head><title>T</title></head><body><p class='intel-empty'>No Geopolitics report has been published yet. Check back soon.</p></body></html>"
    bad = smoke(FakeSite(**{"/daily/geopolitics/2026-10-23": Reply(200, body=page.encode(), ms=5)}))
    assert by_path(bad, "/daily/geopolitics/2026-10-23").severity == "fail" and "fallback copy" in by_path(bad, "/daily/geopolitics/2026-10-23").notes[0]
    assert by_path(bad, "/daily/ai/2026-10-22").severity == "ok"                                     # HTML carries the phrase only inside a <script>


def test_an_error_page_and_a_page_without_a_title_fail() -> None:
    rep = smoke(FakeSite(**{"/live": Reply(200, body=b"<html><body>Application error: a server-side exception has occurred</body></html>", ms=5)}))
    notes = " ".join(by_path(rep, "/live").notes)
    assert by_path(rep, "/live").severity == "fail" and "not a complete HTML" in notes and "fallback copy" in notes


def test_a_stale_marker_on_a_hub_is_a_warning_not_a_failure() -> None:
    page = HTML.replace("fine page", "<span class='fresh-age is-stale'>9 days ago</span>")
    rep = smoke(FakeSite(**{"/": Reply(200, body=page.encode(), ms=5)}))
    assert rep.ok and by_path(rep, "/").severity == "warn"


def test_slow_pages_warn_and_a_dead_site_fails_everything() -> None:
    rep = smoke(FakeSite(**{"/globe": Reply(200, body=HTML.encode(), ms=flags.SLOW_MS + 1)}))
    assert rep.ok and by_path(rep, "/globe").severity == "warn" and "slow" in by_path(rep, "/globe").notes[0]
    dead = smoke(lambda url: Reply(0, error="TimeoutError: timed out", ms=25000))
    assert not dead.ok and dead.count("fail") == len(dead.results) and "no answer" in dead.results[0].notes[0]


def test_a_fetcher_that_raises_is_a_failed_check_not_a_crash() -> None:
    def boom(url):
        raise RuntimeError("socket on fire")

    rep = smoke(boom)
    assert not rep.ok and "RuntimeError" in rep.results[0].notes[0]


def test_api_envelope_rules() -> None:
    good = json.loads(envelope())
    assert checks.envelope_problems(good) == []
    assert "no meta block" in checks.envelope_problems({"data": 1})
    assert "data is empty" in checks.envelope_problems({"data": [], "meta": good["meta"]})
    assert any("error envelope" in p for p in checks.envelope_problems({"error": {"code": "not_found", "message": "x"}, "meta": {"version": "v1"}}))
    assert "meta.cite_as missing" in checks.envelope_problems({"data": 1, "meta": {k: v for k, v in good["meta"].items() if k != "cite_as"}})
    rep = smoke(FakeSite(**{f"/api/v1/entity?name={flags.ENTITY_PROBE}": Reply(200, body=b"<html>oops</html>", ms=5),
                            "/api/v1/theaters?limit=1": Reply(404, body=b'{"error":{"code":"not_found","message":"x"},"meta":{"version":"v1"}}', ms=5)}))
    assert not rep.ok
    assert by_path(rep, f"/api/v1/entity?name={flags.ENTITY_PROBE}").notes == ["body is not JSON"]
    assert by_path(rep, "/api/v1/theaters?limit=1").severity == "fail"


def test_freshness_is_judged_against_the_product_cadence() -> None:
    cad = checks.cadence_minutes("dailies")
    assert cad == 1440
    assert checks.lateness("2026-10-21", "dailies", NOW) == ""                                         # 48 h from the start of today: inside 3 cadences
    assert "dailies as of 2026-10-18" in checks.lateness("2026-10-18", "dailies", NOW)
    assert checks.lateness("2026-10-23T05:30:00Z", "dailies", NOW) == ""
    assert "unreadable" in checks.lateness("soon", "dailies", NOW)
    assert checks.lateness("2020-01-01", "profiles", NOW) == ""                                         # no timer, no cadence, nothing to be late for
    old = smoke(FakeSite(**{"/api/v1/daily/geopolitics/latest": Reply(200, body=envelope(as_of="2026-10-10"), ms=5),
                            "/api/v1/track-record": Reply(200, body=envelope(as_of="2026-09-01"), ms=5)}))
    assert by_path(old, "/api/v1/daily/geopolitics/latest").severity == "fail"                          # the dailies are a hard failure
    assert by_path(old, "/api/v1/track-record").severity == "warn" and old.count("fail") == 1


def test_a_retired_route_must_redirect_to_the_right_place() -> None:
    rep = smoke(FakeSite(**{"/intel": Reply(200, body=HTML.encode(), ms=5), "/ai": Reply(308, {"location": "https://x.example/elsewhere"}, ms=5)}))
    assert by_path(rep, "/intel").severity == "fail" and by_path(rep, "/ai").severity == "fail"
    assert by_path(rep, "/geopolitics").severity == "ok"


def test_robots_feed_and_sitemap_are_validated() -> None:
    rep = smoke(FakeSite(**{"/robots.txt": Reply(200, body=b"User-agent: * allow everything", ms=5), "/feed.xml": Reply(200, body=b"<rss", ms=5)}))
    assert by_path(rep, "/robots.txt").severity == "fail" and by_path(rep, "/feed.xml").severity == "fail"
    nosite = smoke(FakeSite(**{"/sitemap.xml": Reply(500, body=b"", ms=5)}))
    assert by_path(nosite, "/sitemap.xml").severity == "fail" and nosite.unsampled          # no sitemap: no samples, which is reported, and the run goes on


def test_unsampled_templates_are_notes_not_failures() -> None:
    rep = smoke(FakeSite())
    assert "/intel/events/[date]/[theater]/[n]" in rep.unsampled and rep.ok
    assert "no sample for" in rep.text()


def test_base_must_be_http() -> None:
    with pytest.raises(ValueError):
        run.normalise("ohmega.monster")
    assert run.normalise("https://x.example/") == "https://x.example"


# ── state, the doctor row, the cli ───────────────────────────────────────────────────────────
def test_state_records_failures_and_logs_only_changes(tmp_path) -> None:
    sp, home = tmp_path / "s.json", tmp_path
    good = smoke(FakeSite())
    state.record(good, path=sp, home=home)
    assert not (home / "ops-log.md").exists()                                                       # routine green runs stay out of the journal
    bad = smoke(FakeSite(**{"/pulses": Reply(500, ms=5)}))
    st = state.record(bad, path=sp, home=home)
    assert st["ok"] is False and st["failing"] and st["since_failure"] == bad.at
    state.record(bad, path=sp, home=home)
    state.record(good, path=sp, home=home)
    log = (home / "ops-log.md").read_text(encoding="utf-8")
    assert log.count("FAIL") == 2 and "recovered" in log and "/pulses" in log
    assert state.read(sp)["ok"] is True and state.read(sp)["last_ok_at"] == good.at
    assert state.age_hours(state.read(sp), NOW) is not None


def test_the_cli_exits_nonzero_on_failure_and_only_production_runs_are_logged(monkeypatch, capsys, tmp_path) -> None:
    site = FakeSite(**{"/pulses": Reply(500, ms=5)})
    monkeypatch.setattr(run, "default_fetch", site)
    monkeypatch.setattr(flags, "PACE_S", 0)
    saved = []
    monkeypatch.setattr(state, "record", lambda report, **kw: saved.append(report.base))
    real = run.run
    monkeypatch.setattr(run, "run", lambda base=None, **kw: real(base, fetch=site, now=NOW, pace=0, sleep=lambda _s: None))
    args = type("A", (), {"base": BASE, "json": False, "log": True})()
    assert cli.run_smoke(args) == 1
    assert "FAILED" in capsys.readouterr().out and saved == []                                          # a preview is never recorded as the site's state
    args.json = True
    assert cli.run_smoke(args) == 1
    assert json.loads(capsys.readouterr().out)["counts"]["fail"] == 1
    assert cli.run_smoke(type("A", (), {"base": "nope", "json": False, "log": False})()) == 2
