-- 002 — the research corpus, as documents first.
--
-- Profiles go in whole (JSONB) with the fields we query indexed beside them. Claims, sources and
-- entities are extracted into their own tables only when a real query needs them — designing the
-- perfect normal form for data whose future shape we do not know yet is the classic migration trap.
-- Every revision is kept: the profile corpus is append-only history, as on disk.

create table research_profiles (
    id              text primary key,
    title           text not null default '',
    revision        integer not null default 1,
    as_of           text not null default '',
    profile_status  text not null default '',
    generated_at    timestamptz,
    payload         jsonb not null,                      -- the canonical profile document
    ingested_at     timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
create index research_profiles_generated on research_profiles(generated_at);

create table research_profile_revisions (
    profile_id   text not null references research_profiles(id),
    revision     integer not null,
    payload      jsonb not null,
    recorded_at  timestamptz not null default now(),
    primary key (profile_id, revision)
);

alter table research_profiles          enable row level security;
alter table research_profile_revisions enable row level security;
