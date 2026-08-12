"""The radar queue: urgency decides release, and a sweep never arrives as a burst."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from algent_backend.publishing import radar_queue as q


def _post(key: str, urgency: str = "today") -> q.RadarPost:
    return q.RadarPost(key=key, text=f"post {key}", urgency=urgency)  # type: ignore[arg-type]


def test_a_sweep_is_spread_out_but_live_goes_immediately(tmp_path) -> None:
    """Spacing is not delay. A live event is worth something BECAUSE it is early — holding it
    an hour to look less like a bot throws away the only advantage it had."""
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    path = tmp_path / "q.jsonl"

    added, _ = q.enqueue(
        [_post("a"), _post("b"), _post("c"), _post("live1", "live")], path=path, now=now,
    )
    by_key = {p.key: datetime.fromisoformat(p.scheduled_for) for p in added}

    assert by_key["live1"] == now                      # no waiting behind the queue
    assert by_key["a"] > now and by_key["b"] > by_key["a"] and by_key["c"] > by_key["b"]
    # Each ordinary post is meaningfully apart — not a metronome, but not a burst either.
    assert (by_key["b"] - by_key["a"]) >= timedelta(minutes=35)


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
    added, _ = q.enqueue([_post("a"), _post("b"), _post("live", "live")], path=path, now=now)

    # At the moment of the sweep only the live one is releasable.
    assert [p.key for p in q.due(path, now=now)] == ["live"]
    # After a long gap the backlog is all due — a machine that was asleep catches up.
    assert len(q.due(path, now=now + timedelta(hours=6))) == 3

    live = next(p for p in added if p.key == "live")
    q.mark(live.id, status="posted", url="https://x.com/x/status/1", path=path)
    assert q.due(path, now=now + timedelta(hours=6)) and all(
        p.key != "live" for p in q.due(path, now=now + timedelta(hours=6))
    )
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


def test_every_post_is_stamped_radar_exactly_once() -> None:
    """The label is applied by the harness so it cannot drift or be duplicated.

    It says what KIND of post this is — a short notice off the wire — which is honest framing.
    That is the opposite of "BREAKING:", which asserts an urgency the item usually lacks.
    """
    from algent_backend.agent_system.agents.radar import sweep as s

    result = s.RadarSweep(posts=[
        s.RadarSweep.model_fields["posts"].annotation.__args__[0](
            source_key="k1", text="A 7.6 quake hit off Colombia's coast."),
        s.RadarSweep.model_fields["posts"].annotation.__args__[0](
            source_key="k2", text="Radar: the model prefixed it itself."),
    ])

    class _Model:
        def with_structured_output(self, _schema):
            return self

        def invoke(self, _messages):
            return result

    class _Resolver:
        def resolve(self, _spec):
            return type("R", (), {"client": _Model()})()

    out = s.sweep_pool({"items": [{"id": "k1", "label": "x", "channel": "gkg"}]},
                       resolver=_Resolver())
    texts = [p.text for p in out.posts]
    assert texts[0].startswith("Radar: A 7.6 quake")
    # Not "Radar: Radar: ..." when the model stamped it too.
    assert texts[1] == "Radar: the model prefixed it itself."
