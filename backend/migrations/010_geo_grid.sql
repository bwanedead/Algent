-- 010 — Geoledger: merged duplicates and the per-country grid-impact rollup (docs/architecture/geoledger.md).
--
--   geo_assets.merged_into   set by the publisher when `newsroom geo merge DUP INTO` joined two spellings of one place; the
--                            duplicate's row stays (its events point at the target now) but readers hide it.
--   geo_grid                 one tiny row per country: Ohmega's own rollup of installed capacity claimed struck / reported /
--                            confirmed damaged / restored over 7 and 30 days, by fuel (provenance ohmega_derived). Upserted by
--                            the backend; the public `anon` role may only SELECT.
-- Apply BEFORE deploying the site build that reads these columns.

alter table geo_assets add column merged_into text;
create index geo_assets_merged on geo_assets(merged_into) where merged_into is not null;

create table geo_grid (
    iso        text primary key,                    -- ISO 3166-1 alpha-2
    as_of      date not null,
    doc        jsonb not null,                      -- the rollup document (grid.rollup)
    updated_at timestamptz not null default now()
);

alter table geo_grid enable row level security;
create policy geo_grid_public_read on geo_grid for select to anon using (true);
revoke insert, update, delete, truncate on geo_grid from anon, authenticated;
grant select on geo_grid to anon;
