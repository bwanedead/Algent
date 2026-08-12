"""The radar queue: urgency decides release, and a sweep never arrives as a burst."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from algent_backend.publishing import radar_queue as q


def _post(key: str) -> q.RadarPost:
    return q.RadarPost(key=key, text=f"post {key}")


def test_a_sweep_is_spread_out_rather_than_fired_as_a_burst(tmp_path) -> None:
    """One cadence for everything. An earlier design had a live fast lane, but it needed the
    model to judge liveness off a pool line — which it cannot, not knowing the pool's age — and
    a misclassification that GRANTS priority is worse than having none."""
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    path = tmp_path / "q.jsonl"

    added, _ = q.enqueue([_post("a"), _post("b"), _post("c")], path=path, now=now)
    times = [datetime.fromisoformat(p.scheduled_for) for p in added]

    assert times == sorted(times) and times[0] > now
    assert all(b - a >= timedelta(minutes=q._SPACING_MIN) for a, b in zip(times, times[1:]))


def test_a_second_sweep_does_not_interleave_into_the_first_one_s_gaps(tmp_path) -> None:
    """Scheduling from the last pending slot, not from now — otherwise two sweeps in an hour
    undo each other's spacing and the timeline gets a burst anyway."""
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    path = tmp_path / "q.jsonl"

    first, _ = q.enqueue([_post("a"), _post("b")], path=path, now=now)
    last_first = max(datetime.fromisoformat(p.scheduled_for) for p in first)

    second, _ = q.enqueue([_post("c")], path=path, now=now + timedelta(minutes=5))
    assert datetime.fromisoformat(second[0].scheduled_for) > last_first


def test_the_same_source_item_is_never_queued_twice(tmp_path) -> None:
    """Dedup is by SOURCE key, not text: pools are reused across runs, and the same item
    phrased two ways is still the same item posted twice."""
    path = tmp_path / "q.jsonl"
    q.enqueue([_post("quake-7-6")], path=path)

    again = q.RadarPost(key="quake-7-6", text="a completely different wording")
    added, dupes = q.enqueue([again], path=path)

    assert added == [] and len(dupes) == 1
    assert len(q.load(path)) == 1


def test_only_what_is_due_drains_and_posting_is_recorded(tmp_path) -> None:
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    path = tmp_path / "q.jsonl"
    added, _ = q.enqueue([_post("a"), _post("b"), _post("c")], path=path, now=now)

    # Nothing is due the instant it is queued — that is the whole point of spacing.
    assert q.due(path, now=now) == []
    # After a long gap the backlog is all due: a machine that was asleep catches up.
    assert len(q.due(path, now=now + timedelta(hours=6))) == 3

    first = added[0]
    q.mark(first.id, status="posted", url="https://x.com/x/status/1", path=path)
    later = q.due(path, now=now + timedelta(hours=6))
    assert len(later) == 2 and all(p.id != first.id for p in later)
    assert q.summary(path)["by_status"]["posted"] == 1


def test_a_torn_line_never_takes_the_whole_queue_down(tmp_path) -> None:
    """A half-written line is a lost post, not a lost queue."""
    path = tmp_path / "q.jsonl"
    q.enqueue([_post("a"), _post("b")], path=path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"key": "torn", "text": \n')

    assert {p.key for p in q.load(path)} == {"a", "b"}


def test_x_counts_urls_at_a_fixed_width_not_their_real_length() -> None:
    """t.co rewrites every link, so a long article slug costs the same as a short one. Counting
    raw characters would reject postable text and accept unpostable text."""
    from algent_backend.publishing.x_client import LIMIT, billable_length

    long_url = "https://www.ohmega.monster/articles/" + "a" * 200
    text = f"Something happened, and here is why it matters. {long_url}"

    assert len(text) > LIMIT              # naive counting would refuse this
    assert billable_length(text) < LIMIT  # X will accept it


def test_a_gap_leaves_a_backlog_due_but_it_drains_one_at_a_time(tmp_path) -> None:
    """The laptop-was-off case.

    The schedule is on disk, so after a gap everything whose slot has passed is due at once.
    That is correct and must NOT become a burst: a release tick sends exactly one post, so ten
    overdue items go out one per tempo interval rather than all at once.
    """
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    path = tmp_path / "q.jsonl"
    q.enqueue([_post(k) for k in "abcde"], path=path, now=now)

    # Six hours later - the machine was asleep through every slot.
    back = now + timedelta(hours=6)
    ready = q.due(path, now=back)
    assert len(ready) == 5

    # Releasing is one-at-a-time by construction: the daemon takes the earliest and stops.
    first = sorted(ready, key=lambda p: p.scheduled_for)[0]
    q.mark(first.id, status="posted", url="https://x.test/1", path=path)
    assert len(q.due(path, now=back)) == 4

    # And the queue still knows the order it was judged in, so a backlog drains oldest-first.
    remaining = sorted(q.due(path, now=back), key=lambda p: p.scheduled_for)
    assert [p.key for p in remaining] == ["b", "c", "d", "e"]
