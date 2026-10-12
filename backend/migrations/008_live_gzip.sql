-- Live map snapshots are published gzipped (vessels/aircraft/coverage/trails: ~5x smaller), as application/gzip.
-- Migration 006 allowed only images + JSON, so every *.json.gz upload was rejected (400) and the site fell back to
-- stale plain JSON. Allow gzip in the same public, read-only bucket; nothing else about its policy changes.
update storage.buckets
   set allowed_mime_types = array_append(allowed_mime_types, 'application/gzip')
 where id = 'published-assets'
   and not ('application/gzip' = any(allowed_mime_types));
