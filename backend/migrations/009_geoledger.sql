-- 009 — Geospatial asset ledger: what the site's theater maps read (docs/architecture/geoledger.md).
--
-- Two tables written by the backend (`newsroom geo publish`, the daily's extraction step) with the backend credential
-- (bypasses RLS); the public `anon` role may only SELECT. No personal data: places (power plants, substations, refineries,
-- ports, bases...) and dated statements about their state, each with the party who said it and its source URLs.
--
--   geo_assets        one row per place or named thing. Seeded from open data (WRI Global Power Plant Database, CC BY 4.0;
--                     OpenStreetMap, ODbL) and grown by extraction (provenance = 'ohmega_derived', position approximate).
--                     The latest status is denormalised onto the row (status, status_on, status_by, events) so a map reads
--                     one table to colour a place; it is derived from geo_asset_events by the publisher, never edited.
--   geo_asset_events  append-only status events: asset, day, status, CLAIMANT, confidence, sources. A claim ('claimed_struck')
--                     is never a confirmation; the publisher inserts each event once (on conflict do nothing) and never
--                     updates one.

create table geo_assets (
    id            text primary key,                   -- wri-<id> | osm-<n|w|r><id> | og-<iso>-<type>-<slug>
    name          text not null,
    aliases       text[] not null default '{}',
    type          text not null,                      -- power_plant | substation | refinery | fuel_depot | port | bridge | airbase | military_base | dam | rail_hub | vessel | entity | other
    country       text not null default '',           -- ISO 3166-1 alpha-2
    lat           double precision,                   -- null for a thing with no known place (a vessel, an entity)
    lon           double precision,
    loc_precision text not null default 'approximate',-- exact | approximate | city_level | unplaced
    capacity_mw   real,
    fuel          text not null default '',
    attrs         jsonb not null default '{}'::jsonb,
    source        text not null default '',
    licence       text not null default '',
    provenance    text not null default 'aggregated', -- aggregated | ohmega_derived
    status        text,                               -- latest event's status; null = no event on record
    status_on     date,
    status_by     text,
    events        integer not null default 0,
    updated_at    timestamptz not null default now()
);
create index geo_assets_pos     on geo_assets(lat, lon);
create index geo_assets_country on geo_assets(country, type);
create index geo_assets_events  on geo_assets(events) where events > 0;

create table geo_asset_events (
    id          text primary key,                     -- ev-<hash of asset, day, status, claimant>: the same claim is stored once
    asset_id    text not null references geo_assets(id),
    occurred_on date not null,
    occurred_at text not null default '',             -- HH:MM when a source gives the hour
    status      text not null,                        -- operational | claimed_struck | reported_damaged | confirmed_damaged | destroyed | restored | unknown | seized | designated
    claimant    text not null,                        -- who says it: 'Russian MoD', 'Ukrenergo', 'Ohmega analysis'
    confidence  text not null default 'medium',       -- low | medium | high
    sources     text[] not null default '{}',
    provenance  text not null default 'aggregated',
    observed_at timestamptz not null default now(),
    note        text not null default '',
    via         text not null default ''
);
create index geo_asset_events_asset on geo_asset_events(asset_id, occurred_on desc);
create index geo_asset_events_day   on geo_asset_events(occurred_on desc);

alter table geo_assets       enable row level security;
alter table geo_asset_events enable row level security;

create policy geo_assets_public_read       on geo_assets       for select to anon using (true);
create policy geo_asset_events_public_read on geo_asset_events for select to anon using (true);

-- Read-only for the public roles, by grant as well as by policy: no write privilege exists to be misused.
revoke insert, update, delete, truncate on geo_assets, geo_asset_events from anon, authenticated;
grant select on geo_assets       to anon;
grant select on geo_asset_events to anon;
