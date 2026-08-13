# Radar — local invariants

- **Dedup is mechanical, not LLM.** Source `key` catches the same t0 item phrased two ways. Tweet `body_key(text)` (stamp + prefix peel + casefold) catches two wires that became the same sentence. Both gates live in `publishing/radar_queue.py` (`enqueue`, `already_said`, `remembered_bodies`).
- The queue-review model is fail-open and is **not** memory. Do not add another prompt pass to “remember what we posted.”
- Posted rows and skipped rows whose note is duplicate/already-said **are** the record. A 403 duplicate means skip and move on — never leave the item queued to retry forever.
- `Radar:` is applied by `stamp()`, never by the model. Fingerprint after stamp so queued text and bytes on the wire compare equal.
