-- 012 — Sanctions designations and the forward-looking calendar.
--
--   sanctions_events  one row per designation / delisting found by diffing the OFAC SDN list, the UK Sanctions List and the EU
--                     consolidated financial sanctions list against their previous snapshots (backend/algent_backend/sanctions/).
--                     Append-only: a row is never updated. `on_date` is the designation date when the list states a recent one,
--                     otherwise the day Ohmega's diff saw the change (`observed_on`). `baseline` marks rows found in a source's first
--                     snapshot (the list dated them itself). Countries are ISO2. `asset_id` points at the geoledger vessel asset.
--   calendar_items    dated upcoming things (elections, central-bank decisions, summits, UN Security Council meetings, OPEC+ meetings,
--                     deadlines Ohmega extracted from its own daily reports) from backend/algent_backend/lookahead/. One row per
--                     item; `active` goes false when its source stops listing it (a date moved or was cancelled). `confidence` is
--                     high for an official schedule, medium for a list compiled from press reports, low for text we extracted.
--
-- Written by the worker with the backend credential; the public `anon` role may only SELECT. No personal data.
-- Apply BEFORE deploying the site build that reads these tables.

create table sanctions_events (
    id           text primary key,                     -- sx-<hash>: deterministic, the same change found twice is one row
    source       text not null check (source in ('ofac', 'uk', 'eu')),
    action       text not null check (action in ('designated', 'delisted')),
    on_date      date not null,
    observed_on  date not null,
    ref          text not null,                        -- the list's own id for the party
    name         text not null,
    type         text not null check (type in ('person', 'entity', 'vessel', 'aircraft')),
    programmes   text[] not null default '{}',
    countries    text[] not null default '{}',
    imo          text not null default '',
    flag         text not null default '',
    owner        text not null default '',
    source_url   text not null,
    baseline     boolean not null default false,
    asset_id     text,
    created_at   timestamptz not null default now()
);
create index sanctions_events_day on sanctions_events(on_date desc);
create index sanctions_events_source on sanctions_events(source, on_date desc);

create table calendar_items (
    id           text primary key,                     -- cal-<hash> of kind, source and title/date
    on_date      date not null,                        -- the day, or the first day of a window
    end_date     date,                                 -- last day of a window (a summit, a multi-day meeting); null = a single day
    title        text not null,                        -- at most 10 words
    kind         text not null check (kind in ('election', 'central_bank', 'summit', 'security_council', 'opec', 'deadline', 'vote')),
    countries    text[] not null default '{}',         -- ISO2
    theaters     text[] not null default '{}',         -- theater ids from the daily that mentioned it (extracted items)
    source       text not null,                        -- fed | ecb | boe | elections | unsc | opec | corpus
    source_url   text not null,
    confidence   text not null default 'high' check (confidence in ('high', 'medium', 'low')),
    provenance   text not null default 'aggregated' check (provenance in ('aggregated', 'ohmega_derived')),
    via          text not null default '',             -- extracted items: daily:<date>:<theater>
    active       boolean not null default true,
    first_seen   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);
create index calendar_items_day on calendar_items(on_date) where active;

alter table sanctions_events enable row level security;
alter table calendar_items   enable row level security;
create policy sanctions_events_public_read on sanctions_events for select to anon using (true);
create policy calendar_items_public_read   on calendar_items   for select to anon using (true);
revoke insert, update, delete, truncate on sanctions_events, calendar_items from anon, authenticated;
grant select on sanctions_events to anon;
grant select on calendar_items   to anon;
