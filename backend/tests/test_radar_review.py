"""The radar queue review — drops only ids it was actually shown."""

from __future__ import annotations

from algent_backend.agent_system.agents.radar import review as rv


class _Post:
    def __init__(self, post_id: str, text: str = "a post"):
        self.id = post_id
        self.text = text


def test_a_review_cannot_drop_an_id_it_was_not_shown() -> None:
    """The model once invented an id. Acting on it would be deleting a post we did not ask about."""
    pending = [_Post("aaa")]

    class _Model:
        def with_structured_output(self, _schema):
            return self

        def invoke(self, _messages):
            return rv.QueueReview(drop=[
                rv.QueueVerdict(post_id="aaa", reason="stale"),
                rv.QueueVerdict(post_id="zzz", reason="invented"),
            ])

    class _Resolver:
        def resolve(self, _spec):
            return type("R", (), {"client": _Model()})()

    out = rv.review_queue(pending, [], resolver=_Resolver())
    assert [d.post_id for d in out.drop] == ["aaa"]


def test_an_empty_queue_is_a_noop() -> None:
    out = rv.review_queue([], ["already posted"])
    assert out.drop == [] and out.note == "empty queue"
