-- 013 — Maritime behaviour events: what vessels did that is worth a second look (backend/algent_backend/maritime/).
--
--   maritime_events  one row per behaviour event Ohmega derived from the AIS it hears (provenance `ohmega_derived`; no model, no source says it):
--                      ais_gap     a vessel underway went silent for hours in water where other ships kept being heard (receiver loss,
--                                  ports and stream outages are screened out); closed when it is heard again, with how far it reappeared
--                      sts         two vessels, at least one a tanker, alongside each other at near-zero speed for hours in open water
--                                  (ports and crowds of waiting ships are screened out)
--                      identity    a rename, an alternating name, a changed or invalid IMO number, or one IMO under several flag states
--                      sanctioned  a vessel on our board matching a sanctions designation, by IMO or by exact name plus flag state
--                      loiter      a long slow dwell inside a chokepoint or an undersea cable / pipeline corridor (cable boxes are proxies)
--                    Each row carries a confidence (0..1), the one-sentence rationale with the numbers behind it, the plain summary, the detail
--                    numbers each detector used and the evidence points ([unix seconds, lat, lon, knots, note]). An event is a pattern seen,
--                    never a finding of intent. Rows are current plus those ended within the last 30 days; the backend prunes older ones.
--                    MMSI and positions are what vessels broadcast publicly. Written by the worker with the backend credential; the public
--                    `anon` role may only SELECT.
-- Apply BEFORE deploying the site build that reads this table.

create table maritime_events (
    id          text primary key,                      -- mb-<hash>: deterministic, the same behaviour found again updates one row
    kind        text not null check (kind in ('ais_gap', 'sts', 'identity', 'sanctioned', 'loiter')),
    mmsi        bigint not null,
    mmsi2       bigint,                                -- the partner of an STS pair, or the second MMSI of a flag hop
    name        text not null default '',
    name2       text not null default '',
    imo         text not null default '',
    flag        text not null default '',              -- ISO2 from the MMSI's country prefix
    flag2       text not null default '',
    ship_class  text not null default '',              -- tanker | cargo | passenger | fishing | military | other
    started_at  timestamptz not null,
    ended_at    timestamptz,                           -- null = still going
    last_seen   timestamptz,
    state       text not null default 'ongoing' check (state in ('ongoing', 'ended', 'unresolved')),
    active      boolean not null default true,
    lat         double precision,
    lon         double precision,
    area        text not null default '',              -- the named area it lies in ('' = open ocean outside every named area)
    countries   text[] not null default '{}',          -- the desk's names for that area
    confidence  double precision not null default 0,
    rationale   text not null default '',
    summary     text not null default '',
    detail      jsonb not null default '{}'::jsonb,
    evidence    jsonb not null default '[]'::jsonb,
    provenance  text not null default 'ohmega_derived',
    updated_at  timestamptz not null default now()
);
create index maritime_events_active on maritime_events(active, confidence desc);
create index maritime_events_start on maritime_events(started_at desc);
create index maritime_events_kind on maritime_events(kind, started_at desc);
create index maritime_events_mmsi on maritime_events(mmsi);
create index maritime_events_imo on maritime_events(imo) where imo <> '';

alter table maritime_events enable row level security;
create policy maritime_events_public_read on maritime_events for select to anon using (true);
revoke insert, update, delete, truncate on maritime_events from anon, authenticated;
grant select on maritime_events to anon;
