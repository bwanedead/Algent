"""Local-first publishing: nothing is uploaded that the server does not also hold (the 42 charts lost with Supabase), and the free repair
(`intel daily --date D --rerender`) that re-sends what was kept. Offline."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from algent_backend.agent_system.agents.intel import daily_rerender, visuals, visuals_store
from algent_backend.publishing import asset_store

from test_intel_daily_rerender import AS_OF, _basemap, day  # noqa: F401 - the `day` fixture
from test_intel_native_forms import _ask, _attach, _story, _timeline

PKG = Path(visuals.__file__).resolve().parents[3]

#: Every module (relative to algent_backend/) that sends bytes to the object store, and how it keeps a server copy first. A new uploader that is
#: not listed fails ``test_every_uploader_is_registered``: add it here WITH its local store, or write one first.
UPLOADERS = {
    "agent_system/agents/intel/visuals.py": "every producer's uploader goes through visuals_store.local_first -> intel_store/visuals/<domain>/<date>/ (backed up)",
    "satellite/run.py": "chips are read back FROM satellite_store/chips/ (written by observe); the document is written to doc.json before",
    "live/snapshots.py": "derived and replaced every few minutes from the live board; named local copies via `local=`; live_store holds the sources",
    "cli/newsroom/intel.py": "`daily --rerender` re-sends files READ FROM intel_store/visuals/ (visuals_store.republish); it originates nothing",
    "database/diet.py": "legacy Postgres mode: packs documents from database rows, off while POSTGRES_PUBLISH is False",
    "publishing/publish.py": "article assets come from the run dir and are staged to content/articles in the same call (_write_article); db-mode failure aborts",
    "publishing/published_db.py": "documents are built from the staged files under .site-live (site_* stores are backed up)",
    "publishing/rebuild.py": "rebuild-all republishes FROM the local stores; it never originates a document",
    "publishing/site_data.py": "documents built from the domain stores (geoledger, sanctions, ...), all backed up",
    "views/publish.py": "every view is written to views_store/ before it is sent (store() then object_docs.publish); derived from backed-up stores, so a lost store is a rebuild",
}
_SENDERS = ("asset_store.upload", "object_docs.publish", "object_docs.publish_article", "object_docs.publish_articles")


def _call_names(tree: ast.AST) -> set[str]:
    """Every dotted attribute reference in the tree (``asset_store.upload`` whether called or handed on as a value)."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            parts, f = [], node
            while isinstance(f, ast.Attribute):
                parts.append(f.attr)
                f = f.value
            if isinstance(f, ast.Name):
                parts.append(f.id)
            out.add(".".join(reversed(parts)))
    return out


def test_every_uploader_is_registered_with_its_local_copy() -> None:
    found = set()
    for path in PKG.rglob("*.py"):
        rel = path.relative_to(PKG).as_posix()
        if rel.startswith(("publishing/object_", "publishing/asset_store")) or "tests" in path.parts:
            continue
        if _call_names(ast.parse(path.read_text(encoding="utf-8", errors="replace"))) & set(_SENDERS):
            found.add(rel)
    assert not (found - set(UPLOADERS)), f"new uploader(s) {sorted(found - set(UPLOADERS))}: write the artifact to a server store first, then register it"
    assert set(UPLOADERS) <= found, f"UPLOADERS names module(s) that no longer upload: {sorted(set(UPLOADERS) - found)}"
    assert all(len(why) > 30 for why in UPLOADERS.values())


def test_the_daily_visuals_have_no_route_around_the_local_write() -> None:
    src = Path(visuals.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    attach = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "attach")
    calls = _call_names(attach)
    assert "visuals_store.local_first" in calls, "attach must wrap the uploader"
    assert "uploader or _upload" not in src and "asset_store.upload(" not in src.replace("local_first(asset_store.upload)", ""), "an upload bypasses local_first"


def test_upload_persists_before_it_sends(tmp_path, monkeypatch) -> None:
    seen = {}

    def fake_upload(files, **_k):
        seen["at_upload"] = visuals_store.load("geopolitics", "2026-10-14")
        return {"assets": len(files), "skipped": 0, "failed": [], "ok": True}

    monkeypatch.setattr(asset_store, "upload", fake_upload)
    path = "/analytics/daily/geopolitics/2026-10-14/anx_dv1.svg"
    assert visuals._upload({path: b"<svg/>"})["ok"]
    assert seen["at_upload"] == {path: b"<svg/>"}                                   # already on disk when the bucket call happened
    assert (visuals_store.day_dir("geopolitics", "2026-10-14") / "anx_dv1.svg").read_bytes() == b"<svg/>"


def test_nothing_is_uploaded_when_the_local_write_fails(monkeypatch) -> None:
    sent = []

    def broken(_files):
        raise OSError("disk full")

    monkeypatch.setattr(visuals_store, "persist", broken)
    secs, rep, _asked, uploads = _attach(visuals.VisualPlan(visuals=[_ask()]), {"Timeline": _timeline()}, uploads=sent)
    assert rep["produced"] == 0 and uploads == [] and any("local write failed" in s for s in rep["skipped"]) and "visuals" not in secs[0]


def test_native_visuals_are_kept_locally_when_published() -> None:
    secs, rep, _asked, uploads = _attach(visuals.VisualPlan(visuals=[_ask()]), {"Timeline": _timeline()})
    v = secs[0]["visuals"][0]
    kept = visuals_store.load("geopolitics", "2026-10-14")
    assert set(kept) == {v["spec"], v["preview"]} == set(uploads[0])
    assert json.loads(kept[v["spec"]])["events"]


def test_rerender_republishes_saved_visuals_and_rebuilds_stills_from_specs() -> None:
    secs, _rep, _asked, _uploads = _attach(visuals.VisualPlan(visuals=[_ask()]), {"Timeline": _timeline()})
    v = secs[0]["visuals"][0]
    record = {"theaters": secs}
    still = visuals_store.day_dir("geopolitics", "2026-10-14") / Path(v["preview"]).name
    still.unlink()                                                                  # the still is gone; the spec is kept
    sent = []
    out = visuals_store.republish("geopolitics", "2026-10-14", record, lambda files: sent.append(files) or {"assets": len(files), "ok": True})
    assert out["rebuilt"] == [v["id"]] and out["missing"] == [] and out["uploaded"] == 2
    assert set(sent[0]) == {v["spec"], v["preview"]} and sent[0][v["preview"]].startswith(b"<svg") and still.is_file()


def test_visuals_never_saved_are_named_not_faked() -> None:
    record = {"theaters": [{"theater_id": "thr_a", "visuals": [
        {"id": "anx_dv20261015_1", "kind": "timeline", "asset": "/analytics/daily/geopolitics/2026-10-15/anx_dv20261015_1.timeline.svg",
         "spec": "/analytics/daily/geopolitics/2026-10-15/anx_dv20261015_1.timeline.json", "preview": "/analytics/daily/geopolitics/2026-10-15/anx_dv20261015_1.timeline.svg"},
        {"id": "anx_dv20261015_2", "kind": "bar", "asset": "/analytics/daily/geopolitics/2026-10-15/anx_dv20261015_2.svg"}]}]}
    sent = []
    out = visuals_store.republish("geopolitics", "2026-10-15", record, lambda files: sent.append(files) or {"assets": 0, "ok": True})
    assert [m["id"] for m in out["missing"]] == ["anx_dv20261015_1", "anx_dv20261015_2"] and sent == [] and out["files"] == 0
    assert all("visuals-only --fresh-visuals" in m["why"] for m in out["missing"])


def test_a_corrupt_saved_spec_is_reported_and_the_rest_still_go() -> None:
    secs, *_ = _attach(visuals.VisualPlan(visuals=[_ask()]), {"Timeline": _timeline()})
    v = secs[0]["visuals"][0]
    (visuals_store.day_dir("geopolitics", "2026-10-14") / Path(v["spec"]).name).write_text("{not json", encoding="utf-8")
    out = visuals_store.republish("geopolitics", "2026-10-14", {"theaters": secs}, lambda files: {"assets": len(files), "ok": True})
    assert out["missing"] and "unreadable" in out["missing"][0]["why"]


def test_a_model_free_rerender_keeps_the_sections_visuals(day, monkeypatch) -> None:  # noqa: F811
    tmp_path, record = day
    path = tmp_path / "intel" / "daily" / "geopolitics" / f"{AS_OF}.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved["theaters"][0]["visuals"] = [{"id": "anx_dv1", "kind": "timeline"}]
    path.write_text(json.dumps(saved), encoding="utf-8")
    res = daily_rerender.rerender("geopolitics", AS_OF, countries=_basemap())
    assert res["report"]["theaters"][0]["visuals"] == [{"id": "anx_dv1", "kind": "timeline"}]
