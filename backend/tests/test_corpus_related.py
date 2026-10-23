"""``RelatedIndex`` (one pass, many lookups) must answer exactly what ``related`` (one self-join per call) answers."""

from __future__ import annotations

from views_fixture import corpus

from algent_backend.corpus.query import graph


def test_the_bulk_index_equals_the_single_entity_query(tmp_path):
    c = corpus(tmp_path)
    idx = graph.RelatedIndex(c.db)
    checked = 0
    for (eid,) in c.db.execute("SELECT id FROM entities").fetchall():
        assert idx.related(eid, limit=50) == graph.related(c.db, eid, limit=50), eid
        checked += 1
    assert checked >= 6
    irgc = idx.related("org:irgc")
    assert {r["entity"] for r in irgc} >= {"country:IR", "person:iran-leader"} and irgc[0]["via"]["documents"] == 1
    assert idx.related("org:irgc", kinds={"person"})[0]["entity"] == "person:iran-leader"
