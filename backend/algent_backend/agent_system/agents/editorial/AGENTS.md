# editorial

- Gate C (comprehension) reads the prose **cold** and, when the piece does not land, **emits the next draft** (`title` / `standfirst` / `body` on `ComprehensionCheck`). It does not telephone findings back to the article drafter.
- The drafter owns first prose, citation repair, and hedging repair. Those need the profile.
- A shorter rewrite is success. Wrap a collection into one named clause; a trimmed member list is not a rewrite. A hollow stub (under the publish word floor, from a real piece) is discarded.
- House grain: default `ARTICLE_DIGEST_MINUTES` (5) / `ARTICLE_DIGEST_WORDS`; earned cap `ARTICLE_DIGEST_CEILING_*` in `newsroom/flags.py` (helpers in `editorial/length.py`). Extra minutes are earned by the focal thing, not an adjacent world. Do not mechanically truncate.
- Fresh reviewer instance after each rewrite; last rewrite ships unread. Bound is `_MAX_REVIEW_LAPS` in `pipeline.py`.
- `_persist_pipeline_artifacts` overwrites `draft.json` (and the draft store) with the shipped draft, including any rewrite. `article.md` is the readable view of the same object.
