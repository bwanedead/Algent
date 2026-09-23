"""The cut: an overlong draft is brought to its planned band before review."""

from __future__ import annotations

from types import SimpleNamespace

from algent_backend.agent_system.agents.editorial import compress as cz


class _Model:
    def __init__(self, body: str) -> None:
        self.body, self.seen = body, []

    def with_structured_output(self, _schema):
        return self

    def invoke(self, messages, config=None):
        self.seen.append(messages[-1].content)
        return cz.Compressed(body=self.body, cut_note="rolled up lists")


def _ctx(model: _Model):
    return SimpleNamespace(model_resolver=SimpleNamespace(resolve=lambda spec: SimpleNamespace(client=model)))


LONG = " ".join(["word"] * 2000)
PLAN = {"read_minutes": 5}          # band tops out at the digest


def test_an_overlong_draft_is_cut_to_its_plan_with_the_measured_count() -> None:
    model = _Model(" ".join(["tight"] * 900))
    draft, rec = cz.compress(_ctx(model), None, {"title": "t", "body": LONG}, PLAN,
                             model_spec=None, min_words=120)
    assert rec["applied"] and rec["new_words"] == 900 and draft["body"].startswith("tight")
    assert "This draft is 2000 words" in model.seen[0]        # it is told the real count


def test_a_draft_within_its_band_is_left_alone() -> None:
    model = _Model("x")
    draft, rec = cz.compress(_ctx(model), None, {"body": "word " * 300}, PLAN,
                             model_spec=None, min_words=120)
    assert not rec["applied"] and model.seen == []             # no call, no spend


def test_a_cut_that_is_not_shorter_or_is_hollow_is_discarded() -> None:
    longer, rec = cz.compress(_ctx(_Model(LONG + " more")), None, {"body": LONG}, PLAN,
                              model_spec=None, min_words=120)
    assert longer["body"] == LONG and rec["reason"] == "not shorter" and not rec["applied"]
    stub, rec = cz.compress(_ctx(_Model("tiny stub")), None, {"body": LONG}, PLAN,
                            model_spec=None, min_words=120)
    assert stub["body"] == LONG and rec["reason"] == "hollow cut discarded"


def test_a_survey_is_judged_against_its_own_larger_band() -> None:
    # Eight members at their own grain can be long; the ceiling does not bind a survey.
    low, high = cz.target_band({"read_minutes": 12, "shape": "survey"})
    assert high > 1500


def test_a_cut_still_over_gets_one_more_pass_with_the_measured_count() -> None:
    class _Seq(_Model):
        def __init__(self, bodies):
            self.bodies, self.seen = list(bodies), []

        def invoke(self, messages, config=None):
            self.seen.append(messages[-1].content)
            return cz.Compressed(body=self.bodies.pop(0), cut_note="claims ~900")

    model = _Seq([" ".join(["a"] * 1400), " ".join(["b"] * 1000)])
    draft, rec = cz.compress(_ctx(model), None, {"body": LONG}, PLAN, model_spec=None, min_words=120)
    assert rec["passes"] == 2 and rec["new_words"] == 1000
    assert "This draft is 1400 words" in model.seen[1] and "measured" in model.seen[1]
