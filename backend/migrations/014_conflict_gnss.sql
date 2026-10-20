-- 014 - Conflict events and GNSS interference (backend/algent_backend/conflict/, gnss/).
--
--   conflict_events  one row per attack / clash / mass-violence event or report, normalised across sources: GDELT (machine-coded from news,
--                    keyless), ReliefWeb (official reports), ACLED and UCDP (curated; keyed, inactive until the operator adds credentials).
--                    `basis` says what kind of record it is (official | third_party | our_count) and `coverage_note` states its limit, so
--                    the site can show provenance next to any number. Located events may carry `assets` (geoledger assets within a few km).
--                    The backend sends at most a bounded number of the most-reported events per day; the local record holds all.
--   gnss_zones       one row per grid cell per day where aircraft report degraded navigation integrity (GNSS interference), derived by Ohmega
--                    from ADS-B (`source = 'ohmega_adsb'`, basis our_estimate) or read from GPSJam's daily file (`source = 'gpsjam'`,
--                    basis third_party). Severity is the share of sampled aircraft reporting degraded accuracy; `flag` marks a zone that is
--                    new or intensifying against that cell's own learned normal. `baseline_since` is when we began collecting.
--                    Written by the worker with the backend credential; the public `anon` role may only SELECT.
-- Apply BEFORE deploying the site build that reads these tables.

create table conflict_events (
    id            text primary key,                    -- cx-<hash>
    source        text not null check (source in ('gdelt', 'reliefweb', 'acled', 'ucdp')),
    on_date       date not null,
    observed_at   timestamptz not null,
    type          text not null check (type in ('bombing', 'airstrike', 'armed_clash', 'assault', 'mass_violence', 'report')),
    code          text not null default '',
    lat           double precision,
    lon           double precision,
    place         text not null default '',
    country       text not null default '',            -- ISO2
    actor1        text not null default '',
    actor2        text not null default '',
    fatalities    integer,                             -- null = the source does not say
    articles      integer not null default 1,
    title         text not null default '',
    urls          text[] not null default '{}',
    coding        text not null check (coding in ('machine', 'curated', 'report')),
    confidence    text not null check (confidence in ('low', 'medium', 'high')),
    basis         text not null check (basis in ('official', 'third_party', 'our_count')),
    coverage_note text not null default '',
    assets        jsonb not null default '[]'::jsonb
);
create index conflict_events_date on conflict_events(on_date desc);
create index conflict_events_country on conflict_events(country, on_date desc);
create index conflict_events_type on conflict_events(type, on_date desc);

create table gnss_zones (
    id             text primary key,                   -- gz-<hash of source|day|cell>
    on_date        date not null,
    source         text not null check (source in ('ohmega_adsb', 'gpsjam')),
    cell           text not null,                      -- 'lat,lon' of the cell's south-west corner (ohmega_adsb) or the H3 index (gpsjam)
    lat            double precision not null,         -- cell centre
    lon            double precision not null,
    size_deg       double precision not null,         -- cell edge in degrees (gpsjam rows: the approximate edge)
    country        text not null default '',
    severity       text not null check (severity in ('low', 'medium', 'high')),
    degraded_share double precision not null,          -- 0..1
    aircraft       integer not null default 0,         -- distinct aircraft behind the share
    flag           text not null default '' check (flag in ('', 'new', 'intensifying')),
    cross_check    text not null default '' check (cross_check in ('', 'agrees', 'not_in_gpsjam')),   -- ohmega_adsb zones: does GPSJam show the cell too
    basis          text not null check (basis in ('our_estimate', 'third_party')),
    coverage_note  text not null default '',
    baseline_since date
);
create index gnss_zones_date on gnss_zones(on_date desc);
create index gnss_zones_source on gnss_zones(source, on_date desc);

alter table conflict_events enable row level security;
alter table gnss_zones enable row level security;
create policy conflict_events_public_read on conflict_events for select to anon using (true);
create policy gnss_zones_public_read on gnss_zones for select to anon using (true);
revoke insert, update, delete, truncate on conflict_events, gnss_zones from anon, authenticated;
grant select on conflict_events, gnss_zones to anon;
