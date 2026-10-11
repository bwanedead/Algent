-- 007 — Live feeds: what the site's /live page reads (docs/guides/worker-server.md, "Live feeds").
--
-- Two tables written by the worker's collectors with the backend credential (bypasses RLS); the public `anon` role may
-- only SELECT (RLS policies limit live_events to active rows). No personal data: events are
-- country-level outages, earthquakes, regional aircraft counts and satellite hotspots; aircraft are aggregated per region,
-- never published per tail number.
--
--   live_events   one row per real-world thing (an outage, a quake, a cluster of aircraft, a fire cell). `active` is true
--                 while its feed still reports it; the public view shows active rows only.
--   live_stats    one row per (series, day): ship transits per chokepoint, aircraft in the air at once per region,
--                 hotspots per box. `partial` marks the day still being counted.

create table live_events (
    id          text primary key,                     -- ioda:IR:1790724000 | usgs:us6000... | adsb:black_sea | firms:...
    feed        text not null,
    kind        text not null,                        -- outage | quake | aircraft | fire
    title       text not null,
    detail      text not null default '',
    lat         double precision,
    lon         double precision,
    countries   text[] not null default '{}',
    severity    text not null default 'info',         -- info | notable | major
    starts_at   timestamptz,
    ends_at     timestamptz,
    source_url  text not null default '',
    source      text not null default '',
    tags        text[] not null default '{}',
    data        jsonb not null default '{}'::jsonb,
    active      boolean not null default true,
    updated_at  timestamptz not null default now()
);
create index live_events_active on live_events(active, kind);
create index live_events_feed on live_events(feed, active);

create table live_stats (
    series_id   text not null,                        -- live_ais_hormuz_transits, live_mil_black_sea, ...
    period      date not null,
    value       double precision not null,
    partial     boolean not null default false,
    name        text not null default '',
    unit        text not null default '',
    kind        text not null default '',             -- ships | tankers | aircraft | aircraft_support | fires
    region      text not null default '',
    lat         double precision,
    lon         double precision,
    source_url  text not null default '',
    updated_at  timestamptz not null default now(),
    primary key (series_id, period)
);
create index live_stats_period on live_stats(period);

alter table live_events enable row level security;
alter table live_stats  enable row level security;

create policy live_events_public_read on live_events for select to anon using (active);
create policy live_stats_public_read  on live_stats  for select to anon using (true);

grant select on live_events to anon;
grant select on live_stats  to anon;
