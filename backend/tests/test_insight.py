"""Figure-first insight lane — not Radar, not a briefing collage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from algent_backend.agent_system.agents.insight.contracts import (
    Critique,
    InsightSpec,
    apply_critique,
    draw_rows,
    spec_key,
)
from algent_backend.agent_system.agents.insight.copy import format_copy
from algent_backend.agent_system.agents.insight.critique import mechanical_ok
from algent_backend.publishing import insight_queue as q
from algent_backend.publishing.insight_engagement import tweet_id_from_url


def _bars() -> InsightSpec:
    return InsightSpec(
        beat="ai_power",
        form="takeaway_bars",
        takeaway="Amazon's Texas campus is 7.65 GW of private generation",
        unit="GW",
        highlight="Amazon Texas",
        rows=[
            {"label": "Amazon Texas", "value": 7.65},
            {"label": "Large US nuclear plant", "value": 1.2},
            {"label": "Austin peak load", "value": 2.9},
        ],
        source_name="EPA permit",
        source_url="https://example.org/permit",
        as_of="2026-08-13",
        warranted=True,
    )


def test_copy_is_the_takeaway_then_the_source() -> None:
    text = format_copy(_bars())
    assert text.startswith("Amazon's Texas campus is 7.65 GW")
    assert "https://example.org/permit" in text
    assert "Radar:" not in text


def test_thin_specs_are_abandoned_before_the_model() -> None:
    assert mechanical_ok(InsightSpec(beat="chips", warranted=False)) == "not warranted"
    empty = InsightSpec(beat="chips", takeaway="hello", warranted=True,
                        source_url="https://x.test", rows=[{"label": "a", "value": 1}])
    assert "two rows" in mechanical_ok(empty)


def test_a_fix_rewrites_the_title_not_the_numbers() -> None:
    spec = _bars()
    out = apply_critique(spec, Critique(verdict="fix", takeaway="The campus is six nuclear plants"))
    assert out.takeaway.startswith("The campus")
    assert out.rows == spec.rows


def test_bar_draw_rows_accept_x_and_y() -> None:
    spec = InsightSpec(
        form="takeaway_bars",
        rows=[{"x": "Plant A", "y": 7.6}, {"label": "Plant B", "value": 1.2}],
        warranted=True,
    )
    rows = draw_rows(spec)
    assert rows[0] == {"label": "Plant A", "value": 7.6}
    assert rows[1] == {"label": "Plant B", "value": 1.2}


def test_muse_schema_forbids_open_row_objects() -> None:
    def walk(node: object) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            assert node.get("additionalProperties") is not True
        for value in node.values():
            walk(value)
            if isinstance(value, list):
                for item in value:
                    walk(item)

    walk(InsightSpec.model_json_schema())
    walk(Critique.model_json_schema())
    from algent_backend.agent_system.agents.insight.contemplate import Brief
    walk(Brief.model_json_schema())


def test_the_same_takeaway_is_not_queued_twice(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(q, "queue_path", lambda: tmp_path / "i.jsonl")
    now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    spec = _bars()
    post = q.InsightPost(key=spec_key(spec), beat=spec.beat, form=spec.form,
                         text=format_copy(spec), takeaway=spec.takeaway)
    added, dupes = q.enqueue([post], now=now)
    assert len(added) == 1 and dupes == []
    again, dupes2 = q.enqueue([
        q.InsightPost(key=spec_key(spec), beat=spec.beat, form=spec.form, text="other"),
    ], now=now + timedelta(hours=4))
    assert again == [] and len(dupes2) == 1


def test_a_due_insight_is_not_starved_by_a_later_radar_post(monkeypatch) -> None:
    from algent_backend.cli.newsroom import insight as ins
    from algent_backend.publishing import briefing_queue as briefing_q
    from algent_backend.publishing import radar_queue as radar_q

    due = datetime(2026, 8, 14, 7, 22, tzinfo=UTC)
    radar = datetime(2026, 8, 14, 7, 26, tzinfo=UTC)
    now = datetime(2026, 8, 14, 7, 45, tzinfo=UTC)
    monkeypatch.setattr(q, "last_posted_at", lambda: None)
    monkeypatch.setattr(radar_q, "last_posted_at", lambda: radar)
    monkeypatch.setattr(briefing_q, "last_posted_at", lambda: None)
    assert ins._quiet_gap_ok(now, scheduled_for=due.isoformat()) is True
    fresh = datetime(2026, 8, 14, 7, 40, tzinfo=UTC)
    assert ins._quiet_gap_ok(now, scheduled_for=fresh.isoformat()) is False


def test_a_pause_file_turns_the_lane_off(tmp_path, monkeypatch) -> None:
    from algent_backend.cli.newsroom import insight as ins

    monkeypatch.setattr(q, "PAUSE_FILE", tmp_path / "insight.pause")
    assert ins.lane_active() is True
    q.request_pause()
    assert q.paused() is True and ins.lane_active() is False
    assert ins.daemon_tick() == ""
    q.clear_pause()
    assert ins.lane_active() is True


def test_tweet_id_comes_off_the_status_url() -> None:
    assert tweet_id_from_url("https://x.com/ohmegamonster/status/2087868377264169402") == (
        "2087868377264169402")
    assert tweet_id_from_url("") == ""


def test_compose_does_not_queue_a_dropped_warrant(tmp_path, monkeypatch) -> None:
    from algent_backend.cli.newsroom import insight as ins

    monkeypatch.setattr(q, "queue_path", lambda: tmp_path / "i.jsonl")
    monkeypatch.setattr(q, "images_dir", lambda: tmp_path / "img")
    monkeypatch.setattr(q, "_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(ins, "produce", lambda **k: (
        InsightSpec(beat="chips", warranted=False, note="thin"), "", ""))
    added, note = ins.compose()
    assert added == [] and "thin" in note
    assert q.load() == []


def test_standing_lenses_are_a_map_not_two_beats() -> None:
    from algent_backend.agent_system.agents.insight.beats import LENSES

    ids = {b["id"] for b in LENSES}
    assert {"energy", "finance", "economics", "mma", "ai_power", "chips"} <= ids
    assert len(ids) > 4


def test_a_beat_can_be_any_slug() -> None:
    assert InsightSpec(beat="MMA / UFC").beat == "mma_ufc"
    assert InsightSpec(beat="housing").beat == "housing"
    assert InsightSpec(beat="").beat == "world"


def test_discovery_seeds_are_optional_lines() -> None:
    from algent_backend.agent_system.agents.insight.seeds import discovery_brief

    text = discovery_brief(
        pool={"items": [{"label": "Fed balance sheet"}]},
        portfolio={"vectors": [{"title": "Grid queue wait"}]},
    )
    assert "pool: Fed balance sheet" in text
    assert "menu: Grid queue wait" in text
    assert discovery_brief(pool={}, portfolio={}) == ""


def test_warrant_doctrine_is_an_open_net() -> None:
    from algent_backend.agent_system.agents.insight.warrant import WARRANT_ROLE

    body = WARRANT_ROLE.casefold()
    assert "tie-break" in body
    assert "prefer these when a table exists" not in body
    assert "contemplated" in body


def test_ambition_rejects_a_reprint() -> None:
    from algent_backend.agent_system.agents.insight.ambition import AMBITION

    body = AMBITION.casefold()
    assert "reprint" in body
    assert "reality" in body


def test_a_brief_renders_the_pick() -> None:
    from algent_backend.agent_system.agents.insight.contemplate import (
        Brief, Candidate, render_brief,
    )

    text = render_brief(Brief(
        climate="Rates are moving.",
        pick=Candidate(question="Is real debt service past defense?",
                       table_hint="Treasury / OMB"),
    ))
    assert "PICK: Is real debt service past defense?" in text
    assert render_brief(Brief()) == ""


def test_insight_start_clears_pause_without_a_second_daemon(tmp_path, monkeypatch) -> None:
    from algent_backend.cli.newsroom import insight as ins
    from algent_backend.publishing import radar_daemon as d

    monkeypatch.setattr(q, "PAUSE_FILE", tmp_path / "insight.pause")
    q.request_pause()
    spawned: list = []
    monkeypatch.setattr(d, "running", lambda: (True, SimpleNamespace(pid=9)))
    monkeypatch.setattr(
        "algent_backend.cli.newsroom.radar.spawn_detached_loop",
        lambda *a: spawned.append(a) or (1, SimpleNamespace(pid=9)),
    )
    assert ins.run_stop(None) == 0
    assert q.paused() is True
    assert ins.run_start(None) == 0
    assert q.paused() is False
    assert spawned == []
