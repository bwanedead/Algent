"""``newsroom publish prune-orphans``: published once, no longer produced -> deleted, within the budget guard; never anything the current build or the registry owns."""

from __future__ import annotations

import json


from algent_backend.database import flags
from algent_backend.publishing import doc_store, object_docs, orphans
from algent_backend.views import publish as views_publish


class FakeStore:
    ident = "r2:test"

    def __init__(self, bucket=(), refuse_after=None):
        self.objects = set(bucket)
        self.deleted: list[str] = []
        self.refuse_after, self.listed = refuse_after, 0

    def delete(self, key):
        if self.refuse_after is not None and len(self.deleted) >= self.refuse_after:
            return False
        self.deleted.append(key)
        self.objects.discard(key)
        return True

    def list(self, prefix=""):
        self.listed += 1
        return [{"key": k, "size": 1, "etag": "", "modified": ""} for k in sorted(self.objects) if k.startswith(prefix)]


CURRENT = [f"views/entity/org/o{i}.json" for i in range(3)] + ["views/home.json"]
ORPHANS = [f"views/entity/place/p{i}.json" for i in range(7)]


def _world(tmp_path, monkeypatch, *, owned=CURRENT, published=(*CURRENT, *ORPHANS)):
    """A views store whose last complete build made ``owned``, and a manifest that says ``published`` went out."""
    root = tmp_path / "views_store"
    root.mkdir()
    (root / "_state.json").write_text(json.dumps({p: ["h", "t"] for p in owned}), encoding="utf-8")
    monkeypatch.setenv("ALGENT_VIEWS_STORE", str(root))
    object_docs._save(object_docs.manifest_path(), {f"{FakeStore.ident}|{p}": "sha" for p in published} | {f"other:ident|{ORPHANS[0]}": "x"})  # noqa: SLF001
    return FakeStore([doc_store.object_key(p) for p in published])


def test_a_dry_run_reports_and_deletes_nothing(tmp_path, monkeypatch) -> None:
    store = _world(tmp_path, monkeypatch)
    res = orphans.prune(dry_run=True, store=store)
    assert res["ok"] and res["orphans"] == 7 and res["this_run"] == 7 and res["owned"] == 4 and res["published"] == 11 and res["deleted"] == 0
    assert store.deleted == [] and res["sample"][0].startswith("views/entity/place/")


def test_only_orphans_go_and_the_manifest_forgets_them(tmp_path, monkeypatch) -> None:
    store = _world(tmp_path, monkeypatch)
    res = orphans.prune(store=store)
    assert res["deleted"] == 7 and res["remaining_after"] == 0 and sorted(store.deleted) == sorted(doc_store.object_key(p) for p in ORPHANS)
    assert all(doc_store.object_key(p) in store.objects for p in CURRENT), "what the current build owns is never touched"
    left = object_docs._load(object_docs.manifest_path())  # noqa: SLF001
    assert all(f"{store.ident}|{p}" in left for p in CURRENT) and not any(f"{store.ident}|{p}" in left for p in ORPHANS)
    assert f"other:ident|{ORPHANS[0]}" in left, "another bucket's record is not ours to edit"
    row = json.loads(orphans.log_path().read_text(encoding="utf-8").splitlines()[-1])
    assert row["deleted"] == 7 and row["prefix"] == "views/"
    assert orphans.prune(store=store)["orphans"] == 0                                           # idempotent


def test_a_run_is_capped_and_the_backlog_spreads_over_days(tmp_path, monkeypatch) -> None:
    store = _world(tmp_path, monkeypatch)
    first = orphans.prune(store=store, limit=3)
    assert first["deleted"] == 3 and first["remaining_after"] == 4
    assert orphans.prune(store=store, limit=3)["deleted"] == 3
    assert orphans.prune(store=store, limit=3)["deleted"] == 1
    assert flags.ORPHAN_PRUNE_MAX_PER_RUN * 30 < 0.15 * flags.R2_FREE_CLASS_A, "a month of daily runs stays a small share of Class A"


def test_the_guard_stopping_a_delete_stops_the_run(tmp_path, monkeypatch) -> None:
    store = _world(tmp_path, monkeypatch)
    store.refuse_after = 2
    res = orphans.prune(store=store)
    assert res["deleted"] == 2 and res["failed"] == orphans.STOP_AFTER_FAILURES and not res["ok"] and "stopped after" in res["note"]
    assert res["remaining_after"] == 5


def test_it_refuses_without_a_current_build_or_for_a_prefix_nobody_owns(tmp_path, monkeypatch) -> None:
    store = _world(tmp_path, monkeypatch, owned=[])
    res = orphans.prune(store=store)
    assert not res["ok"] and "no current build" in res["note"] and store.deleted == []
    monkeypatch.setenv("ALGENT_VIEWS_STORE", str(tmp_path / "nowhere"))
    assert "no current build" in orphans.prune(store=store)["note"]
    res = orphans.prune("daily/", store=store)
    assert not res["ok"] and "no owner" in res["note"] and store.deleted == []


def test_an_object_the_registry_cannot_name_is_never_deleted(tmp_path, monkeypatch) -> None:
    store = _world(tmp_path, monkeypatch, published=(*CURRENT, *ORPHANS, "views/mystery/thing.json"))
    res = orphans.prune(store=store)
    assert res["unrecognised"] == 1 and doc_store.object_key("views/mystery/thing.json") in store.objects


def test_listing_the_bucket_finds_orphans_a_lost_manifest_forgot(tmp_path, monkeypatch) -> None:
    store = _world(tmp_path, monkeypatch, published=CURRENT)
    store.objects |= {doc_store.object_key(p) for p in ORPHANS}                                  # in the bucket, not in the manifest
    assert orphans.prune(dry_run=True, store=store)["orphans"] == 0 and store.listed == 0       # the manifest alone does not LIST
    res = orphans.prune(list_bucket=True, store=store)
    assert store.listed == 1 and res["deleted"] == 7 and all(doc_store.object_key(p) in store.objects for p in CURRENT)


def test_the_complete_views_build_leaves_exactly_the_state_the_owner_reads(tmp_path) -> None:
    """The owner trusts ``_state.json`` to be the complete current key set: a complete build rewrites it to exactly the views it made (views/publish.py)."""
    from algent_backend.views.base import make

    root = tmp_path / "vs"
    v = [make("home", "home", {}, as_of="2026-10-23", sources=[]), make("graph", "graph", {}, as_of="2026-10-23", sources=[])]
    views_publish.publish(v, root=root, dry_run=False, complete=True, http=lambda *a: 200)
    state = json.loads((root / views_publish.STATE_FILE).read_text(encoding="utf-8"))
    assert set(state) == {"views/home.json", "views/graph.json"}
    views_publish.publish(v[:1], root=root, complete=False, http=lambda *a: 200)
    assert set(json.loads((root / views_publish.STATE_FILE).read_text(encoding="utf-8"))) == {"views/home.json", "views/graph.json"}, "a partial build never shrinks the state"


def test_the_daily_job_is_registered_as_housekeeping_and_uses_the_command() -> None:
    from algent_backend.ops.products import views

    p, job = views.job("orphan-prune")
    assert p.id == "views" and job.prio == 4 and job.preemptible and job.argv == ("publish", "prune-orphans", "--prefix", "views/")
