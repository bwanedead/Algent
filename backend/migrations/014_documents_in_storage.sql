-- 014 — Documents move to Storage; Postgres keeps an index row (docs/architecture/database-budget.md).
--
-- The free plan's database is capped at 500 MB, and the desk's JSON documents (dailies 1-3 MB, dossiers ~0.8 MB x 26, actors, feeds,
-- ~15-40 MB rewritten per publish) filled it. `published_intel_documents` now holds only a small INDEX row per document; the body
-- is a gzipped object in the public `published-assets` bucket under `docs/<path>.gz` (migration 006 bucket, 008 gzip mime;
-- nothing to change there: its one select policy already covers every object of the bucket).
--
--   body        now nullable: null once the document is in Storage. Legacy rows keep their body until `newsroom db diet` moves it,
--               so the site reads either (lib/store.ts: storage_key wins, else body, else the content files).
--   storage_key the object key in the bucket (docs/<path>.gz); null while the body is still inline.
--   size_bytes  uncompressed size of the canonical JSON.
--   sha256      hash of that canonical JSON: the writer skips an upload when it is unchanged (no churn).
--
-- RLS and grants are unchanged (select where visible, to anon): the new columns are as public as the documents themselves.

alter table published_intel_documents alter column body drop not null;
alter table published_intel_documents add column if not exists storage_key text;
alter table published_intel_documents add column if not exists size_bytes  integer;
alter table published_intel_documents add column if not exists sha256      text;

-- The churny tables are small but rewritten constantly; make autovacuum act at ~5% dead rows instead of the default 20% so dead
-- tuples and WAL do not pile up on a nearly full free-plan disk.
alter table live_events      set (autovacuum_vacuum_scale_factor = 0.05, autovacuum_vacuum_threshold = 50);
alter table live_stats       set (autovacuum_vacuum_scale_factor = 0.05, autovacuum_vacuum_threshold = 50);
alter table live_anomalies   set (autovacuum_vacuum_scale_factor = 0.05, autovacuum_vacuum_threshold = 50);
alter table maritime_events  set (autovacuum_vacuum_scale_factor = 0.05, autovacuum_vacuum_threshold = 50);
alter table published_intel_documents set (autovacuum_vacuum_scale_factor = 0.05, autovacuum_vacuum_threshold = 50);
