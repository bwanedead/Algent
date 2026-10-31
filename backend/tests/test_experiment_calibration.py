"""Calibration policies, the lab and live boards, and the no-peeking rule (temp stores, no model calls)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from algent_backend.cli.newsroom import lab as lab_cli
from algent_backend.experiment import calibrate, calibration, flags, policies, score, store
from algent_backend.experiment.calibration import Fitter, Obs, Pool
from algent_backend.experiment.contracts import Question, Resolution, RunRecord

T0 = datetime(2026, 1, 1, 12, tzinfo=UTC)


def at(day: float) -> str:
    return (T0 + timedelta(days=day)).isoformat(timespec="seconds")


@pytest.fixture(autouse=True)
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "lab"))
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "markets"))


def proto(name: str = "mind"):
    return policies.compose(name, [policies.make("model", "m", 1, {"x": 1}), policies.make("prediction", "probability-yes", 1, {"p_min": 0.01, "p_max": 0.99})])


def seed(pid: str, items: list[tuple[float, int]], *, gap_days: float = 1.0, market_p: float = 0.3) -> list[str]:
    """One stored question + resolution + run per (p, outcome): the i-th question is decided at day i * gap and asked 2 days earlier."""
    ids = []
    for i, (p, o) in enumerate(items):
        qid = f"q{i:03d}"
        end = at(i * gap_days + 2)
        q = Question(id=qid, text=qid, cutoff=at(i * gap_days), closes_at=end, source=f"market:{qid}", reference={"market_p": market_p})
        store.write_once(f"questions/{qid}.json", q)
        store.write_once(f"resolutions/{qid}.json", Resolution(question_id=qid, outcome="yes" if o else "no", rule="t", resolved_at=end, recorded_at=end))
        rid = f"r-{pid[:6]}-{qid}"
        store.write_once(f"runs/{rid}/run.json", RunRecord(run_id=rid, question_id=qid, protocol_id=pid, branch_id="b", snapshot="s", manifest_digest="m", prompt_digest="p", output_digest="o", p=p))
        ids.append(qid)
    return ids


LEAN = [(0.06 + 0.02 * (i % 4), 1 if i % 2 == 0 else 0) for i in range(40)]      # says 6-12%, happens half the time: a strong NO bias


def test_platt_pulls_a_systematic_lean_toward_what_happened_and_is_stable_at_small_n():
    obs = [Obs(p, o, at(i), str(i)) for i, (p, o) in enumerate(LEAN)]
    m = calibration.platt_map(obs, calibration.platt().params)
    assert m.fitted and m(0.08) > 0.3                                         # 8% said, ~50% happened
    nudged = calibration.platt_map(obs[:12], calibration.platt().params)
    assert nudged.fitted and 0.08 < nudged(0.08) < m(0.08) + 0.2              # a ridge: few points move it less than a lot, and never past the data
    honest = [Obs(0.5, i % 2, at(i)) for i in range(40)]
    assert calibration.platt_map(honest, calibration.platt().params)(0.3) == pytest.approx(0.3, abs=0.08)       # an already calibrated forecaster is left nearly alone


def test_too_little_data_is_the_identity_and_says_why():
    few = [Obs(0.1, i % 2, at(i)) for i in range(5)]
    m = calibration.platt_map(few, calibration.platt().params)
    assert not m.fitted and m(0.1) == 0.1 and m.kind == "too_few" and "needs" in m.reason
    one_sided = [Obs(0.1, 0, at(i)) for i in range(30)]
    m2 = calibration.platt_map(one_sided, calibration.platt().params)
    assert not m2.fitted and m2.kind == "one_sided" and m2(0.4) == 0.4
    assert calibration.identity_map([], {})(0.37) == 0.37


def test_policies_are_versioned_content_addressed_and_the_protocol_keeps_its_raw_runs():
    a, b = calibration.platt(), calibration.platt()
    assert a.digest == b.digest and a.kind == "calibration" and a.ref == "calibration/platt@1"
    assert calibration.platt_live(("x",)).digest != calibration.platt_live().digest        # different live strategies is a different policy version
    base = proto()
    child = policies.replace_policy(base, calibration.platt(), "mind+platt")
    raw, cal = calibration.split(child)
    assert raw.id == base.id == calibration.base_id(child) and cal.name == "platt" and child.id != base.id
    assert calibration.split(base) == (base, None)


def test_no_peeking_a_cutoffs_map_ignores_every_outcome_resolved_at_or_after_it():
    early = [Obs(p, o, at(i), f"e{i}") for i, (p, o) in enumerate(LEAN[:20])]
    cutoff = at(19.5)                                                                # the first 20 resolved by day 19; nothing after
    pv = calibration.platt()
    base = Pool(early).map_for(pv, cutoff)
    late_a = [Obs(0.9, 1, at(21), "l1"), Obs(0.9, 1, at(22), "l2"), Obs(0.9, 1, cutoff, "at-cutoff"), Obs(0.9, 1, "", "unknown-time")]
    late_b = [Obs(0.1, 0, at(21), "l1"), Obs(0.1, 0, at(22), "l2"), Obs(0.1, 0, cutoff, "at-cutoff"), Obs(0.1, 0, "", "unknown-time")]
    for extra in (late_a, late_b):                                                   # whatever those later outcomes are, the map is bit-for-bit the same
        got = Pool(early + extra).map_for(pv, cutoff)
        assert (got.a, got.b, got.n) == (base.a, base.b, base.n) and base.n == 20
    assert len(Pool(early).before(at(0))) == 0 and len(Pool(early).before(at(0.0001))) == 1      # strictly before, in time order


def test_no_peeking_on_the_lab_board_a_later_outcome_cannot_change_an_earlier_forecast():
    pid = proto().id
    seed(pid, LEAN)
    cal = lambda: calibrate.evaluate([r for r in calibrate.lab_rows() if r["question"] == "q025"], Fitter(lab=calibrate.observations(calibrate.lab_rows())), calibration.platt())  # noqa: E731
    first = cal()
    # flip the outcome of every question decided after q025's cutoff; q025's calibrated forecast must not move
    for i in range(26, 40):
        qid = f"q{i:03d}"
        res = store.read_json(f"resolutions/{qid}.json")
        store.path(f"resolutions/{qid}.json").unlink()
        store.write_once(f"resolutions/{qid}.json", {**res, "outcome": "no" if res["outcome"] == "yes" else "yes"})
    assert cal()["calibrated"]["brier"] == first["calibrated"]["brier"]
    # and the question's OWN outcome is not used for its own map either
    rows = calibrate.lab_rows()
    mine = next(r for r in rows if r["question"] == "q025")
    m = Pool(calibrate.observations(rows)).map_for(calibration.platt(), mine["cutoff"])
    assert m.n == len([r for r in rows if store.parse_time(r["resolved_at"]) < store.parse_time(mine["cutoff"])])


def test_lab_board_puts_raw_and_calibrated_side_by_side_and_counts_what_was_really_recalibrated():
    pid = proto().id
    seed(pid, LEAN)
    board = calibrate.lab_board()
    ev = board["protocols"][pid]["policies"]
    assert set(ev) == {"identity", "platt", "platt-live"}
    assert ev["identity"]["change_in_brier_minus_market"] == 0 and ev["identity"]["n_fitted"] == 0
    pl = ev["platt"]
    assert pl["n"] == 40 and 0 < pl["n_fitted"] < 40 and pl["why_not_fitted"]["too_few"] > 0            # early questions had nothing to learn from
    assert pl["calibrated"]["brier_minus_market"] < pl["raw"]["brier_minus_market"] and pl["change_in_brier_minus_market"] < 0
    assert pl["raw"]["bins"][0]["mean_p"] < 0.15 and pl["raw"]["bins"][0]["hit_rate"] >= 0.4              # the lean the findings describe
    only = calibrate.lab_board(only={"q030", "q031"})["protocols"][pid]["policies"]["platt"]
    assert only["n"] == 2 and only["n_fitted"] == 2                                                   # scoring a subset still fits on the whole past
    assert "platt" in calibrate.render_lab(board) and "negative beats" in calibrate.render_lab(board)


def forecast(strategy, market, at_, p, mkt):
    return SimpleNamespace(strategy=strategy, market_id=market, at=at_, p=p, market=mkt)


def market(mid, outcome, resolved_at):
    return SimpleNamespace(id=mid, status="resolved", outcome=outcome, resolved_at=resolved_at)


def live_fixture():
    fs, ms_ = [], {}
    for i in range(40):                                                               # the same lean in the live bot
        mid = f"m{i}"
        ms_[mid] = market(mid, "yes" if i % 2 == 0 else "no", at(i + 2))
        fs += [forecast("day", mid, at(i + 0.5), 0.3, 0.5), forecast("day", mid, at(i + 1), 0.06 + 0.02 * (i % 4), 0.5)]     # two forecasts: only the last counts
    ms_["open"] = SimpleNamespace(id="open", status="open", outcome="", resolved_at="")
    fs.append(forecast("day", "open", at(1), 0.5, 0.5))
    fs.append(forecast("other", "m3", at(6), 0.9, 0.4))                                # made AFTER m3 resolved: never counted
    return fs, ms_


def test_live_rows_take_the_last_forecast_before_resolution_per_strategy_and_market():
    fs, ms_ = live_fixture()
    rows = calibrate.live_rows(forecasts=fs, markets=ms_)
    assert len(rows) == 40 and {r["strategy"] for r in rows} == {"day"}
    assert all(r["p"] < 0.2 for r in rows) and all(r["cutoff"] < r["resolved_at"] for r in rows)
    assert len(calibrate.live_rows(("other",), forecasts=fs, markets=ms_)) == 0


def test_live_board_scores_the_live_bots_and_says_what_recalibration_would_have_done():
    fs, ms_ = live_fixture()
    board = calibrate.live_board(rows=calibrate.live_rows(forecasts=fs, markets=ms_))
    g = board["groups"]["day"]
    assert g["n"] == 40 and g["raw"]["n_vs_market"] == 40 and 0 < g["n_fitted"] < 40
    assert g["calibrated"]["brier_minus_market"] < g["raw"]["brier_minus_market"]
    head = board["headline"]
    assert head["n"] == 40 and head["calibrated"] < head["raw"] and "instead of" in head["text"] and "40 resolved" in head["text"]
    assert "day" in calibrate.render_live(board)


def test_track_block_is_plain_numbers_and_the_cli_writes_it(capsys, monkeypatch):
    pid = proto().id
    seed(pid, LEAN)
    fs, ms_ = live_fixture()
    real = calibrate.live_rows
    monkeypatch.setattr(calibrate, "live_rows", lambda strategies=(), **k: real(strategies, forecasts=fs, markets=ms_))
    block = calibrate.track_block()
    assert block["best"]["protocol"] == "mind" and block["best"]["n"] == 40 and block["best"]["calibrated"] < block["best"]["raw"]
    assert block["live"]["n"] == 40 and block["live"]["bins_raw"] and block["live"]["bins_calibrated"]
    assert lab_cli.run_block(SimpleNamespace()) == 0
    written = json.loads(store.path(calibrate.BLOCK).read_text(encoding="utf-8"))
    assert written["live"]["text"] == block["live"]["text"]
    assert lab_cli.run_calibrate(SimpleNamespace(qset=None, live_strategies="", json=False)) == 0
    assert "platt" in capsys.readouterr().out


def test_score_restricted_helpers_still_agree_with_the_scoreboard():
    pid = proto().id
    ids = seed(pid, LEAN[:6])
    sb = score.scoreboard(only=set(ids))
    raw = calibrate.lab_board(only=set(ids))["protocols"][pid]["policies"]["identity"]["raw"]
    assert sb["modes"]["controlled"]["protocols"][pid]["brier"] == raw["brier"]
    assert flags.CALIB_MIN_FIT >= 5
