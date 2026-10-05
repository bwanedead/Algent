"""Theater lineage: branches and merges are validated, recorded, and visible; nothing is deleted."""

from __future__ import annotations

import json
from datetime import date

from algent_backend.agent_system.agents.intel import dossier, focus, heat, lineage, sensing
from algent_backend.agent_system.agents.intel.contracts import Theater
from algent_backend.agent_system.agents.statements import store as st_store
from algent_backend.agent_system.agents.statements.contracts import Statement, statement_id

from test_intel import EDITIONS
from test_intel_dossier import _dev, _inputs, _report, _section

TODAY = date(2026, 9, 28)
BRANCH_IDS = ["2026-09-27-2200#1", "2026-09-27-2200#2"]
PARENT_IDS = ["2026-09-28-2200#1", "2026-09-22-2200#1"]


class _Model:
    """A fake clustering model that records the task it was given."""

    def __init__(self, plan):
        self.plan, self.tasks = plan, []

    def with_structured_output(self, _s):
        return self

    def invoke(self, messages, **_k):
        self.tasks.append(messages[-1].content)
        return self.plan


def _ctx(model):
    return type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": model})()})()})()


def _reg() -> dict:
    return {"thr_nato": {"name": "Russia vs NATO", "description": "Russia's pressure on NATO's eastern flank",
                         "first_seen": "2026-09-01", "last_seen": "2026-09-20", "last_novel": "2026-09-20",
                         "state": "active", "domain": "geopolitics"},
            "thr_baltic": {"name": "Baltic security", "description": "Baltic states and Russia",
                           "first_seen": "2026-09-05", "last_seen": "2026-09-20", "last_novel": "2026-09-20",
                           "state": "active", "domain": "geopolitics"}}


def _run(tmp_path, monkeypatch, plan, reg=None):
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path / "intel"))
    monkeypatch.setenv("ALGENT_STATEMENTS_STORE", str(tmp_path / "statements"))
    monkeypatch.setattr(sensing, "for_theater", lambda *a, **k: sensing.Evidence())
    heat._save_registry(reg if reg is not None else _reg())
    model = _Model(plan)
    board = heat.run(_ctx(model), None, EDITIONS, model_spec=None, days=7, today=TODAY)
    return board, heat.registry(), model


# ── validation ────────────────────────────────────────────────────────────────────────────────
def test_resolve_rejects_bad_ids_self_merges_and_cycles() -> None:
    reg = _reg()
    reg["thr_old"] = {"name": "Old", "merged_into": "thr_nato"}
    # a branch needs a tracked parent; an unknown one is dropped, the theater still exists
    assert lineage.resolve("", "", "thr_ghost", "thr_k", reg) == lineage.Resolved(id="thr_k")
    assert lineage.resolve("", "", "thr_nato", "thr_k", reg).parent_id == "thr_nato"
    # a parent that was merged away is followed to its survivor
    assert lineage.resolve("", "", "thr_old", "thr_k", reg).parent_id == "thr_nato"
    # a reused theater is not re-parented
    assert lineage.resolve("thr_baltic", "", "thr_nato", "thr_x", reg) == lineage.Resolved(id="thr_baltic")
    # merges: unknown target, self, and a target already folded into this theater (a cycle) all do nothing
    assert lineage.resolve("thr_baltic", "thr_ghost", "", "x", reg).merged == []
    assert lineage.resolve("thr_baltic", "thr_baltic", "", "x", reg).merged == []
    assert lineage.resolve("thr_nato", "thr_old", "", "x", reg) == lineage.Resolved(id="thr_nato")
    ok = lineage.resolve("thr_baltic", "thr_nato", "", "x", reg)
    assert ok.id == "thr_nato" and ok.merged == ["thr_baltic"]
    # a merged-away theater the model still names lands in its survivor
    assert lineage.resolve("thr_old", "", "", "x", reg).id == "thr_nato"
    assert lineage.survivor({"a": {"merged_into": "b"}, "b": {"merged_into": "a"}}, "a") == ""


# ── branch ────────────────────────────────────────────────────────────────────────────────────
def test_a_branch_is_new_keeps_its_parent_and_leaves_the_rest_in_the_parent(tmp_path, monkeypatch) -> None:
    plan = heat.TheaterPlan(theaters=[
        heat.ProposedTheater(existing_id="thr_nato", name="Russia vs NATO", headline_ids=PARENT_IDS),
        heat.ProposedTheater(name="Kaliningrad", parent_id="thr_nato", why="its own escalation path",
                             headline_ids=BRANCH_IDS)])
    board, reg, _ = _run(tmp_path, monkeypatch, plan)
    by_id = {t["id"]: t for t in board["theaters"]}
    assert by_id["thr_kaliningrad"]["parent_id"] == "thr_nato" and len(by_id["thr_nato"]["members"]) == 2
    assert reg["thr_kaliningrad"]["parent_id"] == "thr_nato" and reg["thr_kaliningrad"]["first_seen"] == "2026-09-28"
    assert reg["thr_nato"]["first_seen"] == "2026-09-01"                      # the parent's history is untouched
    child = next(e for e in reg["thr_kaliningrad"]["lineage"] if e["event"] == "branched")
    assert child == {"event": "branched", "role": "child", "other_id": "thr_nato", "at": "2026-09-28",
                     "why": "its own escalation path"}
    assert {"event": "branched", "role": "parent", "other_id": "thr_kaliningrad"}.items() <= \
        reg["thr_nato"]["lineage"][0].items()
    # heat starts from its own members only; it is a fresh theater, so lifecycle says new
    row = next(h for h in board["heat"] if h["theater_id"] == "thr_kaliningrad")
    assert row["total"] == 2 and row["state"] == "new" and reg["thr_kaliningrad"]["state"] == "new"
    assert [e["theater_id"] for e in board["lineage"]] == ["thr_kaliningrad", "thr_nato"]


def test_a_branch_needs_two_headlines_and_a_known_parent(tmp_path, monkeypatch) -> None:
    plan = heat.TheaterPlan(theaters=[
        heat.ProposedTheater(name="Lone", parent_id="thr_nato", headline_ids=BRANCH_IDS[:1]),
        heat.ProposedTheater(name="Orphan", parent_id="thr_ghost", headline_ids=BRANCH_IDS)])
    board, reg, _ = _run(tmp_path, monkeypatch, plan)
    assert [t["id"] for t in board["theaters"]] == ["thr_orphan"]
    assert "parent_id" not in reg["thr_orphan"] and "lineage" not in reg["thr_nato"]


# ── merge ─────────────────────────────────────────────────────────────────────────────────────
def test_a_merge_keeps_the_absorbed_theater_but_moves_clustering_and_focus(tmp_path, monkeypatch) -> None:
    plan = heat.TheaterPlan(theaters=[
        heat.ProposedTheater(existing_id="thr_baltic", merge_into="thr_nato", why="one contest",
                             name="Baltic security", headline_ids=BRANCH_IDS),
        heat.ProposedTheater(existing_id="thr_nato", name="Russia vs NATO", headline_ids=PARENT_IDS)])
    board, reg, _ = _run(tmp_path, monkeypatch, plan)
    assert [t["id"] for t in board["theaters"]] == ["thr_nato"] and len(board["theaters"][0]["members"]) == 4
    assert board["theaters"][0]["name"] == "Russia vs NATO" and board["theaters"][0]["absorbed"] == ["thr_baltic"]
    assert reg["thr_baltic"]["merged_into"] == "thr_nato" and reg["thr_baltic"]["merged_at"] == "2026-09-28"
    assert reg["thr_baltic"]["state"] == focus.MERGED and reg["thr_baltic"]["name"] == "Baltic security"
    assert reg["thr_nato"]["first_seen"] == "2026-09-01"
    assert {"event": "merged", "role": "survivor", "other_id": "thr_baltic"}.items() <= \
        reg["thr_nato"]["lineage"][0].items()
    assert board["lifecycle"] == []                                           # gone from focus, not "quiet"
    # next run: the merged theater is not offered to the model, and naming it anyway lands in the survivor
    plan2 = heat.TheaterPlan(theaters=[heat.ProposedTheater(existing_id="thr_baltic", name="Baltic", headline_ids=BRANCH_IDS)])
    board2, reg2, model = _run(tmp_path, monkeypatch, plan2, reg=reg)
    assert "thr_baltic" not in model.tasks[0] and "thr_nato" in model.tasks[0]
    assert [t["id"] for t in board2["theaters"]] == ["thr_nato"]
    assert len(reg2["thr_nato"]["lineage"]) == 1                              # events are never repeated
    assert "thr_baltic" not in {e["theater_id"] for e in focus.offboard(reg2, set(), as_of=TODAY, days=7)}


def test_a_branch_is_listed_with_its_parent_to_the_model(tmp_path, monkeypatch) -> None:
    reg = _reg()
    reg["thr_k"] = {"name": "Kaliningrad", "parent_id": "thr_nato"}
    assert "(branched from Russia vs NATO)" in lineage.describe_known(reg)


# ── statement-driven nomination ───────────────────────────────────────────────────────────────
def _st(speaker, day, about, *, signal="red_line", text="We will respond") -> Statement:
    url = f"https://src.example/{speaker}/{day}/{about[0]}"
    return Statement(id=statement_id(url, speaker, text + about[0]), speaker=speaker, date=day, paraphrase=text,
                     about=list(about), signal=signal, source_url=url, transcript_id="tr")


def test_nominations_are_only_uncovered_places_and_bounded(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_STATEMENTS_STORE", str(tmp_path))
    rows = [_st("Putin", "2026-09-27", ["Kaliningrad"]), _st("Medvedev", "2026-09-26", ["Kaliningrad"]),
            _st("Lavrov", "2026-09-27", ["NATO"]),                              # covered by Russia vs NATO
            _st("Kallas", "2026-09-27", ["Suwalki"], signal="reassurance"),    # not a red line / threat
            _st("Old", "2026-08-01", ["Narva"])]                                 # outside the window
    rows += [_st(f"S{i}", "2026-09-25", [f"Place{i}"], signal="threat") for i in range(20)]
    st_store.append_statements(rows)
    block = lineage.nominations_block(_reg(), as_of=TODAY)
    assert block.splitlines()[0].startswith("- Kaliningrad (2 statements)")
    assert "NATO" not in block and "Suwalki" not in block and "Narva" not in block
    assert "https://src.example/Putin/2026-09-27/Kaliningrad" in block and "2026-09-27 [red_line] Putin" in block
    assert sum(1 for ln in block.splitlines() if ln.startswith("- ")) == lineage.MAX_NOMINATIONS
    assert len(block.splitlines()) <= lineage.MAX_NOMINATIONS * (1 + lineage.PER_NOMINATION)


def test_the_block_reaches_the_clustering_task_only_when_there_is_something(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_STATEMENTS_STORE", str(tmp_path / "statements"))
    st_store.append_statements([_st("Putin", "2026-09-27", ["Kaliningrad"])])
    _b, _r, model = _run(tmp_path, monkeypatch, heat.TheaterPlan())
    assert "SIGNALS THAT MAY DESERVE THEIR OWN THEATER:\n- Kaliningrad" in model.tasks[0]
    (tmp_path / "statements" / "statements.jsonl").unlink()
    _b, _r, model = _run(tmp_path, monkeypatch, heat.TheaterPlan())
    assert "SIGNALS" not in model.tasks[0]


# ── the dossier ───────────────────────────────────────────────────────────────────────────────
def test_dossiers_carry_lineage_and_a_branch_inherits_history_up_to_its_date() -> None:
    inp = _inputs()
    inp.reports.append(_report("2026-10-05", [_section("thr_kal", "Kaliningrad", [_dev("Kaliningrad drill", when="2026-10-05")])]))
    inp.registry = {
        "thr_alpha": {"name": "Alpha war", "lineage": [{"event": "branched", "role": "parent", "other_id": "thr_kal",
                                                          "at": "2026-09-30", "why": "w"}]},
        "thr_kal": {"name": "Kaliningrad", "parent_id": "thr_alpha", "lineage": [
            {"event": "branched", "role": "child", "other_id": "thr_alpha", "at": "2026-09-30", "why": "its own path"}]},
        "thr_bravo": {"name": "Bravo dispute", "merged_into": "thr_alpha", "merged_at": "2026-10-01", "state": "merged",
                      "first_seen": "2026-09-02", "lineage": [{"event": "merged", "role": "absorbed",
                                                                "other_id": "thr_alpha", "at": "2026-10-01", "why": "same"}]},
    }
    inp.registry["thr_alpha"]["lineage"].append({"event": "merged", "role": "survivor", "other_id": "thr_bravo",
                                                 "at": "2026-10-01", "why": "same"})
    inp.registry["thr_bravo"]["merged_into"] = "thr_alpha"
    built = dossier.build_all(inp)
    kal, alpha, bravo = (built["theaters"][t] for t in ("thr_kal", "thr_alpha", "thr_bravo"))
    assert kal["lineage"]["parent"] == {"theater_id": "thr_alpha", "name": "Alpha war", "at": "2026-09-30",
                                        "why": "its own path", "url": "/intel/theaters/thr_alpha"}
    assert kal["inherited"] and all(t["date"] <= "2026-09-30" for t in kal["inherited"])
    assert [b["theater_id"] for b in alpha["lineage"]["branches"]] == ["thr_kal"]
    assert [a["theater_id"] for a in alpha["lineage"]["absorbed"]] == ["thr_bravo"]
    assert alpha["lineage"]["absorbed"][0]["url"] == "/intel/theaters/thr_bravo"
    assert bravo["lineage"]["merged_into"]["theater_id"] == "thr_alpha" and bravo["state"] == "merged"
    rows = {r["theater_id"]: r for r in built["index"]["theaters"]}
    assert rows["thr_kal"]["parent_id"] == "thr_alpha" and rows["thr_bravo"]["merged_into"] == "thr_alpha"
    assert alpha["lineage"]["parent"] is None and alpha["inherited"] == []
    json.dumps(built)


def test_a_lineage_less_registry_adds_empty_lineage() -> None:
    d = dossier.build_all(_inputs())["theaters"]["thr_alpha"]
    assert d["lineage"] == {"parent": None, "branches": [], "merged_into": None, "absorbed": []}


def test_theater_contract_defaults() -> None:
    t = Theater(id="thr_x", name="X")
    assert t.parent_id == "" and t.absorbed == []
