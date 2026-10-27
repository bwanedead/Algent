"""Acquisition ledger (experiment framework L1): first-seen time per source unit, surviving index rebuilds, read by the lab. Stubbed sources, temp stores."""

from __future__ import annotations

import pytest

from algent_backend.acquisition import store as acq
from algent_backend.experiment import runner, sources
from algent_backend.experiment.contracts import Question


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "lab"))
    monkeypatch.setenv("ALGENT_ACQUISITION_STORE", str(tmp_path / "acq"))
    monkeypatch.setenv("ALGENT_CORPUS_STORE", str(tmp_path / "corpus"))


def _fake_source(units: dict[str, tuple[str, str]]):
    """A corpus source over {unit key: (fingerprint, document body)}, each unit emitting one dated document."""
    from algent_backend.corpus.sources.base import Source, Unit

    def make(key: str, fp: str, body: str) -> Unit:
        return Unit(key=key, fingerprint=fp, date="2026-03-01", emit=lambda sink: sink.document(f"doc:{key}", "daily", date="2026-03-01", title=key, body=body))

    return Source(name="fake", product="dailies", units=lambda: [make(k, fp, b) for k, (fp, b) in units.items()])


def _build(monkeypatch, units, *, full=False):
    import importlib
    build = importlib.import_module("algent_backend.corpus.build")
    from algent_backend.corpus import sources as corpus_sources
    monkeypatch.setattr(corpus_sources, "load", lambda only=None: [_fake_source(units)])
    return build.build(full=full)


def test_ledger_survives_rebuilds_and_marks_the_first_build_as_backfill(monkeypatch):
    r1 = _build(monkeypatch, {"u1": ("f1", "old body")})
    assert r1["acquisition"]["written"] == 1 and r1["acquisition"]["backfill"] is True
    e1 = acq.load()[("u1", "f1")]
    assert e1["backfill"] and acq.acquired_at(e1) == ""                      # the record pre-dated the ledger: acquisition unknown, not "now"
    r2 = _build(monkeypatch, {"u1": ("f1", "old body"), "u2": ("g1", "new")}, full=True)      # a full rebuild resets the index's ingested_at ...
    assert r2["acquisition"]["written"] == 1
    led = acq.load()
    assert led[("u1", "f1")] == e1                                          # ... but never the ledger
    assert led[("u2", "g1")]["backfill"] is False and acq.acquired_at(led[("u2", "g1")])
    _build(monkeypatch, {"u1": ("f2", "edited body")})
    assert ("u1", "f2") in acq.load() and acq.load()[("u1", "f1")] == e1     # an edit is a new entry; the old one stands


def test_a_ledger_failure_never_breaks_a_build(monkeypatch):
    monkeypatch.setattr(acq.Ledger, "flush", lambda self, now: (_ for _ in ()).throw(OSError("disk full")))
    r = _build(monkeypatch, {"u1": ("f1", "x")})
    assert r["acquisition"]["written"] == 0 and "disk full" in r["acquisition"]["error"] and r["rows"]["documents"] == 1


def test_corpus_source_reads_acquired_time_from_the_ledger_not_from_the_index(monkeypatch):
    from algent_backend.corpus import paths
    _build(monkeypatch, {"u1": ("f1", "pre-ledger body")})                                   # backfill: unknown
    _build(monkeypatch, {"u1": ("f1", "pre-ledger body"), "u2": ("g1", "later body")})
    src = sources.CorpusSource(paths.db_file())
    cutoff = "2026-03-02T00:00:00+00:00"
    items = {e.id: e for e in src.candidates(cutoff)}
    assert items["doc:u1"].acquired_at == "" and items["doc:u2"].acquired_at               # known only where the ledger has the unit (and it is not backfill)
    assert src.acquired_known is False and src.n_acquired == 1
    # the later-acquired unit did not exist for us at this cutoff, whatever its publish date says
    sid, visible, meta = runner.build_snapshot(src, Question(id="q", text="t", cutoff=cutoff))
    assert [e.id for e in visible] == ["doc:u1"] and dict(meta["excluded"])["doc:u2"] == "acquired after cutoff" and meta["n_acquired"] == 1
    assert not any(e.acquired_at for e in sources.CorpusSource(paths.db_file(), ledger={}).candidates(cutoff))


def test_the_acquisition_store_is_registered_irreplaceable_and_backed_up():
    from algent_backend.data_backup import sync
    from algent_backend.ops.products import views
    assert "acquisition_store" in sync._sources() and "ALGENT_ACQUISITION_STORE" in views.registered_envs()
