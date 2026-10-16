-- 011 — Live anomalies: where the live feeds depart from Ohmega's own learned normal (backend/algent_backend/live/memory/).
--
--   live_anomalies   one row per CONFIRMED anomaly: a place (a 1-degree cell or a named area), a series (ship.tanker, air.military,
--                    fire.count ...), when it started and whether it is still going, how far from normal (value vs normal, ratio, a plain
--                    sentence), a confidence and the provenance `ohmega_derived` (computed by Ohmega from public sensor feeds; no model,
--                    no source says it). Neighbouring flagged cells are merged into one row. Active rows plus those closed within the
--                    last 14 days are kept; the backend prunes older ones. Written by the worker's hourly memory pass with the backend
--                    credential; the public `anon` role may only SELECT. No personal data: counts of objects per place, never a vessel
--                    or aircraft. Compact by design (tens of rows); the long record lives in the instruments store and on the server.
-- Apply BEFORE deploying the site build that reads this table.

create table live_anomalies (
    id          text primary key,                     -- ship.tanker:gate:hormuz:2026-10-16T04
    series      text not null,                        -- ship.tanker | air.military | fire.count ...
    layer       text not null,                        -- ship | air | fire
    klass       text not null,
    place_kind  text not null,                        -- cell | gate | region | fire
    place_id    text not null,                        -- c12345 (a 1-degree cell) | gate:hormuz | region:black_sea | fire:ukraine_front
    label       text not null,
    lat         double precision,
    lon         double precision,
    countries   text[] not null default '{}',         -- names as the desk writes them (matched against a theater's countries)
    direction   text not null check (direction in ('above', 'below')),
    starts_at   timestamptz not null,
    ends_at     timestamptz,                          -- null = still going
    last_seen   timestamptz,
    active      boolean not null default true,
    hours       integer not null default 1,
    value       double precision not null default 0,  -- latest reading (objects present)
    normal      double precision not null default 0,  -- the median for this hour of the week
    ratio       double precision,                     -- value / normal (null when normal is about zero)
    score       double precision not null default 0,  -- strongest robust z-score
    confidence  double precision not null default 0,  -- 0..1
    learning    boolean not null default false,       -- the baseline is still young (fewer than a full set of weeks)
    n_cells     integer not null default 1,
    sentence    text not null default '',
    provenance  text not null default 'ohmega_derived',
    updated_at  timestamptz not null default now()
);
create index live_anomalies_active on live_anomalies(active, confidence desc);
create index live_anomalies_start on live_anomalies(starts_at desc);

alter table live_anomalies enable row level security;
create policy live_anomalies_public_read on live_anomalies for select to anon using (true);
revoke insert, update, delete, truncate on live_anomalies from anon, authenticated;
grant select on live_anomalies to anon;
