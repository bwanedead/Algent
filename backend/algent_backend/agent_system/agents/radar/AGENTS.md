# Radar — local invariants

- **Dedup is mechanical, not LLM.** Source `key` catches the same t0 item phrased two ways. Tweet `body_key(text)` (stamp then casefold) catches two wires that became the same sentence. Both gates live in `publishing/radar_queue.py` (`enqueue`, `already_said`, `remembered_bodies`).
- The queue-review model is fail-open and is **not** memory. Do not add another prompt pass to “remember what we posted.”
- Posted rows and skipped rows whose note is duplicate/already-said **are** the record. A 403 duplicate means skip and move on — never leave the item queued to retry forever.
- `stamp()` peels a leftover `Radar:` label; it does not add one. Radar is the internal lane name. Fingerprint after stamp so a labeled queued row and an unlabeled send compare equal.
