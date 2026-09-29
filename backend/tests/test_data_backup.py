"""The data backup mirrors adds and updates — and never propagates a deletion."""

from __future__ import annotations

from algent_backend.data_backup import backup, mirror


def test_mirror_adds_and_updates_but_never_deletes(tmp_path) -> None:
    src, dest = tmp_path / "profile_store", tmp_path / "data"
    (src / "_history").mkdir(parents=True)
    (src / "a.json").write_text("v1", encoding="utf-8")
    (src / "_history" / "a.1.json").write_text("old", encoding="utf-8")
    (src / "b.json.tmp").write_text("partial write", encoding="utf-8")

    assert mirror({"profile_store": src}, dest) == 2              # the .tmp is never copied
    assert mirror({"profile_store": src}, dest) == 0              # unchanged: nothing to do
    (src / "a.json").write_text("v2", encoding="utf-8")
    assert mirror({"profile_store": src}, dest) == 1
    assert (dest / "profile_store" / "a.json").read_text(encoding="utf-8") == "v2"

    (src / "_history" / "a.1.json").unlink()                      # an accident locally…
    mirror({"profile_store": src}, dest)
    assert (dest / "profile_store" / "_history" / "a.1.json").exists()   # …never reaches the backup


def test_backup_is_off_in_tests() -> None:
    assert backup()["note"] == "disabled"
