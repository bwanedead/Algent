"""The nightly backup covers exactly the stores of the irreplaceable products in the product registry (``ops/products/registry.py``), and every store
the code writes to belongs to a registered product - the server is the system of record, so a store nobody registered is one dead disk away from
being lost. This test makes that impossible to forget silently."""

from __future__ import annotations

import re
from pathlib import Path

from algent_backend.data_backup import sync
from algent_backend.ops.products import views

PKG = Path(sync.__file__).resolve().parents[1]

#: Folder names whose location follows another store's variable (a subfolder of it).
FOLLOWS = {"maritime_daily": "ALGENT_MARITIME_STORE"}
PUBLISHED = ("site_articles", "site_intel", "site_radar", "site_data")      # what was published exists nowhere else once the database is gone


def _store_envs() -> set[str]:
    found: set[str] = set()
    for path in PKG.rglob("*.py"):
        if "tests" in path.parts:
            continue
        found |= set(re.findall(r"""["'](ALGENT_[A-Z_]*(?:STORE|_DIR))["']""", path.read_text(encoding="utf-8", errors="replace")))
    return found


def test_every_store_the_code_writes_belongs_to_a_registered_product() -> None:
    """A store variable the code reads but no product registers is a store nobody decided to back up, budget or prune."""
    envs = _store_envs()
    unknown = envs - views.registered_envs()
    assert not unknown, f"store variable(s) {sorted(unknown)} belong to no product: add a Store to the owning product in ops/products/registry.py"
    assert views.registered_envs() <= envs, "the registry names a store variable the code no longer has"


def test_coverage_is_exactly_the_stores_of_irreplaceable_products() -> None:
    expected = {s.name for p, s in views.stores() if p.irreplaceable and s.backed_up}
    assert set(sync._sources()) == expected
    for p in views.products():
        if p.irreplaceable:
            assert any(s.backed_up for s in p.stores), f"{p.id} is irreplaceable but backs nothing up"
    reasons = views.excluded_stores()
    assert reasons and all(len(why) > 20 for why in reasons.values()), "every store left out of the backup says why"
    assert not set(reasons) & set(sync._sources())


def test_each_backed_up_store_follows_the_same_location_the_code_writes_to(monkeypatch, tmp_path) -> None:
    envs = {s.name: s.env or FOLLOWS.get(s.name, "") for _, s in views.stores() if s.backed_up}
    for env in set(envs.values()) - {""}:
        monkeypatch.setenv(env, str(tmp_path / env))
    sources = sync._sources()
    for name, env in envs.items():
        if env:
            assert str(sources[name]).startswith(str(tmp_path / env)), f"{name} does not follow {env}"


def test_what_was_published_and_the_corpus_stores_are_mirrored() -> None:
    sources = sync._sources()
    assert set(PUBLISHED) <= set(sources)
    assert {"pulse_store", "geoledger_store", "sanctions_store", "calendar_store", "markets_store", "maritime_daily"} <= set(sources)


def test_the_mirror_copies_new_and_changed_files_and_never_deletes(tmp_path) -> None:
    src, dest = tmp_path / "pulse", tmp_path / "mirror"
    (src / "log").mkdir(parents=True)
    (src / "log" / "a.jsonl").write_text("1\n", encoding="utf-8")
    assert sync.mirror({"pulse_store": src}, dest) == 1
    assert sync.mirror({"pulse_store": src}, dest) == 0
    (src / "log" / "a.jsonl").write_text("1\n2\n", encoding="utf-8")
    (src / "log" / "a.jsonl.tmp").write_text("partial", encoding="utf-8")
    assert sync.mirror({"pulse_store": src}, dest) == 1
    (src / "log" / "a.jsonl").unlink()
    sync.mirror({"pulse_store": src}, dest)
    assert (dest / "pulse_store" / "log" / "a.jsonl").read_text(encoding="utf-8") == "1\n2\n"          # an accident must not propagate
