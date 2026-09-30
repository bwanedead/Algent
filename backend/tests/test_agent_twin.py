"""The agent twin exposes graded claims and citable sources — never source text or internals."""

from __future__ import annotations

import json

from algent_backend.publishing.agent_twin import build_twin, write_twin

PROFILE = {
    "id": "prof_x", "open_questions": ["[unresolved, blocking] internal research note"],
    "source_ledger": [
        {"id": "s_ok", "url": "https://reuters.com/a", "title": "A", "publisher": "Reuters",
         "published_at": "2026-09-01", "safe_to_cite": True,
         "snapshot": {"excerpt": "FULL COPYRIGHTED PAGE TEXT"}},
        {"id": "s_no", "url": "https://x.com/b", "title": "B", "safe_to_cite": False},
    ],
    "claim_ledger": [
        {"id": "clm_1", "text": "Talks  resumed.", "status": "confirmed", "salience": "high",
         "supported_by": ["s_ok", "s_no"], "contradicted_by": [], "note": "internal caveat"},
        {"id": "clm_2", "text": "A weird grade.", "status": "banana", "supported_by": []},
    ],
}
META = {"slug": "talks-abc123", "title": "Talks resume", "dek": "d", "as_of": "2026-09-02",
        "date": "2026-09-02", "status": "publishable",
        "corrections": [{"date": "2026-09-03", "reason": "internal log", "note": "Reworded a date."},
                        {"date": "2026-09-04", "reason": "internal only"}]}


def test_claims_carry_grades_and_only_citable_sources() -> None:
    twin = build_twin(META, PROFILE)
    assert twin["schema"] == "ohmega.article/1" and twin["url"].endswith("/articles/talks-abc123")
    c1 = twin["claims"][0]
    assert c1["text"] == "Talks resumed." and c1["grade"] == "confirmed"
    assert [s["publisher"] for s in c1["sources"]] == ["Reuters"]          # unsafe source withheld
    assert twin["claims"][1]["grade"] == "unconfirmed"                    # unknown grade never inflates
    assert twin["grades"] == {"confirmed": 1, "unconfirmed": 1}


def test_nothing_internal_or_copyrighted_leaks() -> None:
    text = json.dumps(build_twin(META, PROFILE))
    for leak in ("FULL COPYRIGHTED PAGE TEXT", "internal research note", "internal caveat",
                 "internal log", "internal only", "snapshot"):
        assert leak not in text
    assert build_twin(META, PROFILE)["corrections"] == [{"date": "2026-09-03", "note": "Reworded a date."}]


def test_writing_a_twin_updates_the_index(tmp_path) -> None:
    write_twin(tmp_path, build_twin(META, PROFILE))
    index = json.loads((tmp_path / "public" / "data" / "index.json").read_text(encoding="utf-8"))
    assert index["articles"][0]["title"] == "Talks resume" and index["articles"][0]["claims"] == 2
