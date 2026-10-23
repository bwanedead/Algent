"""Maritime daily summaries and the retention of the raw event log: what is kept, what is summarised, nothing double counted. Offline."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from algent_backend.maritime import rollup, store
from algent_backend.maritime.contracts import BehaviourEvent
from algent_backend.maritime.profile import ProfileBook

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_MARITIME_STORE", str(tmp_path / "maritime"))
    monkeypatch.setenv("ALGENT_LIVE_STORE", str(tmp_path / "live"))


def line(event: str, at: str, i: int, kind="ais_gap", conf=0.5, area="Hormuz", started="2026-08-01T00:00:00+00:00") -> str:
    e = BehaviourEvent(id=f"mb-{i}", kind=kind, mmsi=636000000 + i, name=f"S{i}", started_at=started, area=area, confidence=conf, summary=f"sum {i}",
                       evidence=[[k, 26.0 + k / 100, 56.0, 2.0, ""] for k in range(30)])
    return json.dumps({"event": event, "at": at, "e": e.model_dump()}, separators=(",", ":"))


def write_log(lines: list[str]) -> None:
    store.root().mkdir(parents=True, exist_ok=True)
    (store.root() / "log.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_old_lines_become_a_day_summary_and_recent_lines_stay() -> None:
    write_log([line("open", "2026-08-01T01:00:00+00:00", 1), line("open", "2026-08-01T02:00:00+00:00", 2, kind="sts", conf=0.9),
               line("ended", "2026-08-01T05:00:00+00:00", 1), line("open", "2026-10-21T01:00:00+00:00", 3, started="2026-10-21T00:00:00+00:00")])
    dry = rollup.compact_log(now=NOW.timestamp(), apply=False)
    assert dry["lines"] == 4 and dry["kept"] == 1 and dry["summarised"] == 4 and (store.root() / "log.jsonl").exists()
    assert not (store.root() / "daily").exists()                                    # a dry run writes nothing
    done = rollup.compact_log(now=NOW.timestamp(), apply=True)
    assert done["days"] == ["2026-08-01", "2026-10-21"] and done["bytes_after"] < done["bytes_before"]    # a complete day is summarised before it ages out
    kept = (store.root() / "log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(kept) == 1 and json.loads(kept[0])["id"] == "mb-3" and "e" not in json.loads(kept[0])    # rewritten as a compact transition
    day = rollup.read_day("2026-08-01")
    assert day["events"]["opened"] == 2 and day["events"]["by_kind"] == {"ais_gap": 1, "sts": 1} and day["events"]["outcomes"] == {"ended": 1}
    assert day["events"]["gaps_by_area"] == {"Hormuz": 1}
    assert [n["id"] for n in day["notable"]] == ["mb-2"] and len(day["tracks"][0]["pts"]) == rollup.TRACK_POINTS    # a few sampled tracks, not 30 points
    assert not (store.root() / "log.jsonl.work").exists() and not (store.root() / "log.jsonl.kept").exists()


def test_a_second_run_adds_nothing_and_a_late_line_adds_once() -> None:
    write_log([line("open", "2026-08-01T01:00:00+00:00", 1)])
    rollup.compact_log(now=NOW.timestamp(), apply=True)
    again = rollup.compact_log(now=NOW.timestamp(), apply=True)
    assert again["summarised"] == 0 and rollup.read_day("2026-08-01")["events"]["opened"] == 1
    with (store.root() / "log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(line("open", "2026-08-01T09:00:00+00:00", 7) + "\n")
    rollup.compact_log(now=NOW.timestamp(), apply=True)
    assert rollup.read_day("2026-08-01")["events"]["opened"] == 2


def test_lines_written_while_compacting_are_not_lost(monkeypatch) -> None:
    write_log([line("open", "2026-08-01T01:00:00+00:00", 1)])
    real = rollup.write_day

    def writer_appends_meanwhile(day, doc):
        with (store.root() / "log.jsonl").open("a", encoding="utf-8") as fh:        # the stream service, mid-compaction
            fh.write(line("open", "2026-10-22T11:00:00+00:00", 9, started="2026-10-22T10:00:00+00:00") + "\n")
        return real(day, doc)

    monkeypatch.setattr(rollup, "write_day", writer_appends_meanwhile)
    rollup.compact_log(now=NOW.timestamp(), apply=True)
    ids = [json.loads(x)["e"]["id"] for x in (store.root() / "log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert ids == ["mb-9"]


def test_a_crashed_run_resumes_from_the_set_aside_file() -> None:
    store.root().mkdir(parents=True, exist_ok=True)
    (store.root() / "log.jsonl.work").write_text(line("open", "2026-08-01T01:00:00+00:00", 1) + "\n", encoding="utf-8")
    (store.root() / "log.jsonl").write_text(line("open", "2026-10-22T01:00:00+00:00", 2, started="2026-10-22T00:00:00+00:00") + "\n", encoding="utf-8")
    out = rollup.compact_log(now=NOW.timestamp(), apply=True)
    assert out["summarised"] == 1 and rollup.read_day("2026-08-01")["events"]["opened"] == 1
    assert len((store.root() / "log.jsonl").read_text(encoding="utf-8").splitlines()) == 1 and not (store.root() / "log.jsonl.work").exists()


def test_zones_summarise_the_profile_book_by_class_and_speed() -> None:
    from algent_backend.live.memory.areas import AREAS

    zone = next(a for a in AREAS if a.kind == "gate")
    lat, lon = (zone.box[0] + zone.box[2]) / 2, (zone.box[1] + zone.box[3]) / 2
    t = datetime(2026, 10, 21, 10, tzinfo=timezone.utc).timestamp()
    book = ProfileBook()
    for mmsi, typ, sog in ((636000001, 80, 12.0), (636000002, 70, 10.0), (636000003, 80, 0.0)):
        book.identity(mmsi, f"S{mmsi}", "", typ, t)
        p = book.get(mmsi)
        for k in range(3):
            p.samples.extend([int(t) + k * 3600, int(lat * 1e4), int(lon * 1e4), int(sog * 10)])
    day = rollup.zones_of_day(book, "2026-10-21")
    z = day[zone.id]
    assert z["ships"] == 3 and z["by_class"] == {"cargo": 1, "tanker": 2} and z["underway"] == 2 and z["median_kn"] == 11.0 and z["samples"] == 9
    assert rollup.zones_of_day(book, "2026-10-20") == {}


def test_the_store_report_names_the_big_files() -> None:
    write_log([line("open", "2026-08-01T01:00:00+00:00", 1)])
    rep = rollup.store_report()
    assert rep["files"][0]["path"] == "log.jsonl" and rep["total_bytes"] > 0


def test_legacy_churn_collapses_to_transitions_and_counts_once() -> None:
    """The measured shape: opens repeated for one id, 'ongoing' flips. After compaction one open + one end per id, nothing summarised twice."""
    lines = [line("open", f"2026-10-20T0{h}:00:00+00:00", 1, kind="identity") for h in range(5)]                  # same event re-opened 5 times
    lines += [line("ongoing", "2026-10-20T06:00:00+00:00", 2), line("open", "2026-10-20T05:00:00+00:00", 2),
              line("ongoing", "2026-10-20T07:00:00+00:00", 2), line("ended", "2026-10-20T08:00:00+00:00", 2), line("ongoing", "2026-10-20T09:00:00+00:00", 2)]
    write_log(lines)
    dry = rollup.compact_log(now=NOW.timestamp(), apply=False)
    assert dry["opens_before"] == 6 and dry["opens_after"] == 2 and dry["by_kind_after"] == {"identity": 1, "ais_gap": 1}
    done = rollup.compact_log(now=NOW.timestamp(), apply=True)
    out = [json.loads(x) for x in (store.root() / "log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(o["id"], o["state"]) for o in out] == [("mb-1", "open"), ("mb-2", "open"), ("mb-2", "ended")]
    assert set(out[0]) == {"id", "kind", "state", "mmsi", "imo", "name", "ship_class", "at", "lat", "lon", "area", "confidence"}
    ev = rollup.read_day("2026-10-20")["events"]
    assert ev["opened"] == 2 and ev["outcomes"] == {"ended": 1} and ev["through"] == "2026-10-20T08:00:00+00:00" and done["bytes_after"] < done["bytes_before"]
    rollup.compact_log(now=NOW.timestamp(), apply=True)                                                          # idempotent
    assert rollup.read_day("2026-10-20")["events"]["opened"] == 2


def test_a_day_counted_while_complete_is_not_counted_again_when_it_ages_out() -> None:
    write_log([line("open", "2026-10-20T01:00:00+00:00", 1)])
    rollup.compact_log(now=NOW.timestamp(), apply=True)                                                          # day 10-20 is complete: summarised, line kept
    assert rollup.read_day("2026-10-20")["events"]["opened"] == 1
    later = datetime(2026, 11, 5, tzinfo=timezone.utc).timestamp()
    rollup.compact_log(now=later, apply=True)                                                                    # now it ages out
    assert rollup.read_day("2026-10-20")["events"]["opened"] == 1 and not (store.root() / "log.jsonl").read_text(encoding="utf-8")
