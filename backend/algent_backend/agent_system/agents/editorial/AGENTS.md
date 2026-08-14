# editorial

- Gate C (comprehension) reads the prose **cold** and, when the piece does not land, **emits the next draft** (`title` / `standfirst` / `body` on `ComprehensionCheck`). It does not telephone findings back to the article drafter.
- The drafter owns first prose, citation repair, and hedging repair. Those need the profile.
- A shorter rewrite is success. A hollow stub (under the publish word floor, from a real piece) is discarded.
- Fresh reviewer instance after each rewrite; last rewrite ships unread. Bound is `_MAX_REVIEW_LAPS` in `pipeline.py`.
- `_persist_pipeline_artifacts` overwrites `draft.json` (and the draft store) with the shipped draft, including any rewrite. `article.md` is the readable view of the same object.
