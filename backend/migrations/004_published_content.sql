-- 004 — Published content: what the public site reads live (docs/architecture/published-content.md).
--
-- Three tables, and ONLY the first two are readable by the public `anon` role. The corpus, ledgers and
-- Pulse tables stay unreadable: RLS is on with no policy, and nothing is granted. The backend's own
-- credential writes these rows; the site holds only the anon key (public by design).
--
--   published_articles          one row per article slug (the site's markdown file: frontmatter + body + receipts)
--   published_intel_documents   the desk's JSON files (daily, theaters, actors, briefs, snapshots, record),
--                               keyed by their path under the site's intel directory
--   published_article_revisions append-only history of every article write (backend-only: no grant, no policy)
--
-- `visible` is the publish switch: a row is public only while visible. (Retracted articles stay visible —
-- the tombstone is the honest record — so `visible` is for pulling a row off the site entirely.)

create table published_articles (
    slug          text primary key,
    title         text not null,
    status        text not null default '',
    published_at  timestamptz,
    markdown      text not null,
    visible       boolean not null default true,
    updated_at    timestamptz not null default now()
);

create table published_intel_documents (
    path        text primary key,                     -- daily/geopolitics/2026-09-30.json
    kind        text not null,                        -- first path segment: daily | theaters | actors | ...
    body        jsonb not null,
    visible     boolean not null default true,
    updated_at  timestamptz not null default now()
);
create index published_intel_documents_kind on published_intel_documents(kind, path);

create table published_article_revisions (
    id          bigint generated always as identity primary key,
    slug        text not null,
    markdown    text not null,
    created_at  timestamptz not null default now()
);
create index published_article_revisions_slug on published_article_revisions(slug, created_at);

alter table published_articles          enable row level security;
alter table published_intel_documents   enable row level security;
alter table published_article_revisions enable row level security;

create policy published_articles_public_read on published_articles
    for select to anon using (visible);
create policy published_intel_documents_public_read on published_intel_documents
    for select to anon using (visible);

grant select on published_articles        to anon;
grant select on published_intel_documents to anon;
