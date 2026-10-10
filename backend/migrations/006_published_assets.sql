-- 006 — Published assets: a PUBLIC Storage bucket for the images the site shows (docs/architecture/published-content.md).
--
-- Article hero / figure / chart images and anything else the site serves from a file now live in the bucket
-- `published-assets` instead of the git repo, so publishing never needs a commit. They are published images:
-- public read is the point. The bucket is the ONLY thing this migration exposes, and only for SELECT:
--   * the storage policy lets `anon` read objects of this one bucket (no insert/update/delete policy exists, so
--     only the server-side service-role key — which bypasses RLS — can write);
--   * no table is granted, nothing else changes. Corpus, ledgers and Pulse stay unreadable.
-- Size and type limits are a second layer: images (SVGs are sanitised by the backend before upload) and JSON only.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('published-assets', 'published-assets', true, 10485760,
        array['image/svg+xml', 'image/webp', 'image/png', 'image/jpeg', 'image/gif', 'application/json'])
on conflict (id) do update
   set public = true, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists published_assets_public_read on storage.objects;
create policy published_assets_public_read on storage.objects
    for select to anon
    using (bucket_id = 'published-assets');
