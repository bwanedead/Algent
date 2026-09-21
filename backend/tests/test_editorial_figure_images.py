"""Interior illustrations — planned against the prose, placed by anchor, never evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from algent_backend.agent_system.agents.editorial import figure_images as fi

BODY = (
    "## The pyramid in the bay\n\n"
    "Shimizu proposed a stepped lattice rising two kilometres over Tokyo Bay.\n\n"
    "## The ribbon to orbit\n\n"
    "Obayashi's elevator would run a tether well past geostationary height.\n"
)


class _Artifacts:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def write_bytes(self, name: str, data: bytes, kind: str = "") -> None:
        (self.root / name).write_bytes(data)

    def write_json(self, name: str, payload: dict, kind: str = "") -> None:
        (self.root / name).write_text(str(payload), encoding="utf-8")


class _Image:
    data = b"\xff\xd8jpeg"
    model = "gemini-3.1-flash-lite-image"
    estimated_usd = 0.0336
    label = fi.CONCEPT_LABEL

    def suffix(self) -> str:
        return ".jpg"


def _drawer(seen: list[dict[str, Any]]):
    def draw(subject: str, *, setting: str = "", register: str = "concept", **_: Any) -> _Image:
        seen.append({"subject": subject, "setting": setting, "register": register})
        return _Image()
    return draw


def _plan(**over: Any) -> fi.ImagePlan:
    fields = {
        "id": "pyramid", "subject": "a stepped pyramid city rising from a bay",
        "setting": "at dusk", "anchor": "The pyramid in the bay",
        "alt": "A vast stepped pyramid standing in open water",
    }
    return fi.ImagePlan(slots=[fi.ImageSlot(**{**fields, **over})])


def test_the_image_lands_after_the_passage_it_belongs_to(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    figures = fi.make_figures(_plan(), BODY, _Artifacts(tmp_path), generate=_drawer(seen))
    out = fi.place(BODY, figures)

    assert seen[0]["register"] == "concept" and seen[0]["setting"] == "at dusk"
    assert (tmp_path / "figure_pyramid.jpg").is_file()
    heading = out.index("## The pyramid in the bay")
    image = out.index("![A vast stepped pyramid")
    prose = out.index("Shimizu proposed")
    assert heading < image < prose          # under its heading, above the paragraph
    # The file name is the disclosure contract: the site gives every `figure_` image the AI
    # signature (frame, label, page key), so the name must never drift.
    assert "](figure_pyramid.jpg)" in out


def test_a_subject_that_would_draw_data_is_refused(tmp_path: Path) -> None:
    # The same guard as the hero: an image model handed numbers draws numbers, and drawn
    # numbers look like evidence.
    plan = _plan(subject="a chart of 91.5% cost overruns")
    seen: list[dict[str, Any]] = []
    assert fi.make_figures(plan, BODY, _Artifacts(tmp_path), generate=_drawer(seen)) == []
    assert seen == []


def test_an_anchor_the_piece_does_not_contain_is_dropped(tmp_path: Path) -> None:
    # Rather than parking the picture at an arbitrary point in someone else's paragraph.
    plan = _plan(anchor="A section the reviewer cut")
    assert fi.make_figures(plan, BODY, _Artifacts(tmp_path), generate=_drawer([])) == []


def test_several_images_keep_their_own_anchors(tmp_path: Path) -> None:
    plan = fi.ImagePlan(slots=[
        fi.ImageSlot(id="a", subject="a stepped pyramid city in a bay",
                     anchor="The pyramid in the bay", alt="pyramid"),
        fi.ImageSlot(id="b", subject="a slender tether climbing into black sky",
                     anchor="The ribbon to orbit", alt="ribbon"),
    ])
    figures = fi.make_figures(plan, BODY, _Artifacts(tmp_path), generate=_drawer([]))
    out = fi.place(BODY, figures)
    assert out.index("![pyramid]") < out.index("## The ribbon to orbit") < out.index("![ribbon]")


def test_no_slots_is_a_normal_answer(tmp_path: Path) -> None:
    empty = fi.ImagePlan(none_because="nothing physical to picture")
    assert fi.make_figures(empty, BODY, _Artifacts(tmp_path), generate=_drawer([])) == []


def test_an_existing_thing_can_be_illustrated_in_the_editorial_register(tmp_path: Path) -> None:
    # Real photos preferred, but a framed, labelled illustration beats none (operator ruling).
    seen: list[dict[str, Any]] = []
    fi.make_figures(_plan(style="editorial"), BODY, _Artifacts(tmp_path), generate=_drawer(seen))
    assert seen[0]["register"] == "editorial"
