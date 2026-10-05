# Instruments — architecture

> Ohmega's programmatic numbers layer. No model anywhere in it. Vision: `docs/vision/ohmega-intelligence-engine.md`.
> Code: `backend/algent_backend/instruments/`. CLI: `newsroom instruments`. Store style mirrors `docs/architecture/pulse-system.md` (log is truth, state is a projection).

## Why it exists

The intel desk sees ~40 radar headlines a day. The hard numbers that situations actually move — ships through a strait,
a crude price, gas storage, a yield — never reach it, so readings of those situations guess from headlines. Example
(verified 2026-10-04): IMF PortWatch shows Hormuz at 1–7 transits/day since March 2026 against a ~80/day five-year mean.
That is decisive free evidence, with a URL and an as-of date. Instruments turns such series into **cited evidence** that is
cheap enough to refresh several times a day and later feed reports, research, maps, Watches and Pulses (none of that is
wired yet — only clean consumption APIs exist).

## Layout

| Module | Role |
|---|---|
| `contracts.py` | `Series` (catalog metadata) and `Observation` (one reading with provenance), `period_date` |
| `catalog.py` | the curated, code-defined series list grouped by theme; `get_series`, `match(tags)` |
| `sources/<provider>.py` | one fetcher per provider: `fetch(series, since) -> list[Observation]` plus a pure `parse(text, series, fetched_at)`; registered in `sources/__init__.PROVIDERS` |
| `algent_backend/polite_http.py` (shared with `actors/`) | the only HTTP path: browser UA, 60 s timeout, 2 retries, 0.25 s per-host pacing, per-process memo, `SourceError` / `SourceUnavailable` naming the URL |
| `store.py` | append-only JSONL per series |
| `moves.py` | pure maths: changes, percentile, unusual flags |
| `evidence.py` | consumption API: `evidence_block`, `moves_board` |
| `collect.py` | runs providers into the store, failure-isolated |
| `cli/newsroom/instruments.py` | `fetch`, `show`, `moves` (each prints one JSON document) |

## Contracts

`Series`: `id` (permanent; names the store file), `name`, `unit`, `frequency` (daily/weekly/monthly), `source`,
`source_url` (the human page to cite, not the API), `fetcher` (provider module), `params` (provider selector: port, symbol, key…),
`tags` (region + actor + dynamic keywords: `hormuz`, `iran`, `gulf`, `shipping`, `energy`), `licence`, `public_display`.

`Observation`: `series_id`, `period` (`YYYY-MM-DD` or `YYYY-MM`), `value`, `fetched_at`, `source_url`, `revised`.

## Store

`instruments_store/series/<id>.jsonl` under the working directory, or `$ALGENT_INSTRUMENTS_STORE` (same resolution as `intel_store`).
`append` writes a line only for a never-seen period, or for a period whose value **changed** (that line has `revised=true`);
an unchanged re-fetch writes nothing and no line is ever edited. `history()` projects "latest line per period"; "what did we
believe on day D" is a filter on `fetched_at`. (Yahoo's latest bar is the live session, so it is legitimately revised on later fetches.)

Fetch window: normal fetches ask each provider for everything since 14 days before the newest stored period (the overlap
lets revisions surface); first fetch with nothing stored takes the provider's default recent window; `--backfill` asks for
5 years (`BACKFILL_DAYS`), bounded so a one-off fill is a few dozen paced requests (~1–2 min), not an archive crawl.
A provider whose first series fails at network level is skipped for the rest of the run; one failing series never aborts others.

## Moves maths (`moves.py`)

Per series, as of the latest period (or `--as-of`): latest value; change vs previous reading and vs ~7d / ~30d / ~1y earlier
(latest reading on or before that date; horizons shorter than the series' own median spacing are omitted, so a monthly series
has no "7d"); `percentile_1y` (mid-rank within the trailing year); `new_high`/`new_low` = the longest of 30d/90d/1y windows
in which the latest is AT the extreme (ties allowed — a collapse sitting at its low still is at its low; only windows the history covers).

**`unusual` is derived from the series' own history, with no per-series thresholds:**

- `change_z` — latest period-over-period change in std-devs of the earlier changes (log-changes when all values are positive, plain differences otherwise).
- `level_z` — latest value in std-devs of its trailing year (excluding the latest). Catches a sustained collapse no single daily change would.
- `unusual` = either |z| > 2 (conventional two-sigma "outside its own normal"; not fitted) with ≥ 10 earlier observations (a statistical floor so a std-dev means something). Flat history + any departure = unusual.
- `long_run_z` / `long_run_outside` — latest against ALL stored history. Informational, **not** folded into `unusual`: a long regime (Hormuz since March) absorbs the trailing-year mean and hides from `level_z`, but trending series (debt, yields) are "outside" their past by construction and would cry wolf as a flag. It is printed beside the reading instead.

## Consumption API

```python
from algent_backend.instruments import evidence_block, moves_board
evidence_block(["hormuz", "energy"], as_of=None)  # text, one cited line per stored matching series; "" if none
moves_board(tags=None, as_of=None)                # list[dict], unusual first; for the site/maps/watches later
```

Both read the store only (never the network) and accept `as_of` for replay. Lines mark `[internal source]` for
`public_display=False` series; consumers that publish must filter on `public_display`.

## Catalog and licence table

Verdicts are our reading, not legal advice; "verify" means do not show publicly until checked.

| Series (ids) | Provider | Licence note | Verdict |
|---|---|---|---|
| `chk_{hormuz,bab_el_mandeb,suez,panama,malacca,bosporus,cape}_{transits,tanker_transits}` | IMF PortWatch (ArcGIS, keyless, ~1 wk lag, history to 2019) | open data, attribute IMF PortWatch | public with attribution; verify terms page once |
| `px_brent`, `px_wti`, `px_ttf_gas`, `px_henry_gas`, `px_gold`, `px_copper`, `px_wheat`, `fx_dxy`, `fx_usdcny`, `fx_usdrub`, `risk_vix` | Yahoo chart API (unofficial) | no published terms | **internal only** (`public_display=False`) until ToS reviewed; replace with exchange/central-bank sources for public use |
| `rate_ust_2y`, `rate_ust_10y` | US Treasury yield-curve XML | US government work | public domain |
| `fisc_us_debt` | US Treasury FiscalData | US government work | public domain |
| `rate_ecb_deposit`, `fx_eurusd_ecb` | ECB data portal (SDMX csv) | reuse with attribution | public with attribution; verify |
| `infl_ea_hicp` | Eurostat (JSON-stat) | reuse with attribution (Dec. 2011/833/EU) | public with attribution |
| `gas_eu_storage` | GIE AGSI+ | **API key required** (free); attribute GIE | blocked until `ALGENT_AGSI_KEY` set; verify before public display |

Not available: **FRED** csv endpoint disconnects from this machine; **EIA** needs a key. Both skipped (add as providers when keys exist).
GIE AGSI: keyless call returns HTTP 200 with `"Invalid or missing API key"`; the provider refuses without a key and reports the series `blocked`. Its keyed response parser follows GIE's published schema and is unverified against a live key.

## Adding a series

One entry in `catalog.py` (`CATALOG`), choosing tags generously. On an existing provider that is all — e.g. a Yahoo symbol is
`_yahoo(id, name, unit, symbol, tags, page)`; a new chokepoint is one `_chokepoint(...)` line. For a new provider: add
`sources/<name>.py` with `parse` + `fetch`, register it in `sources/__init__.PROVIDERS`, add a captured response to
`backend/tests/fixtures/instruments/` and a parser test.

## Tests

`backend/tests/test_instruments_{sources,store_moves,consumers}.py` — offline: one captured real response per provider, store
append/revision, moves maths on synthetic series (outliers, regimes, short/monthly history), evidence format, collector isolation, CLI smoke on a temp store.

## Consumers

The intelligence desk reads this layer through `agent_system/agents/intel/sensing.py` (read-only; `evidence.render_block` prints chosen `moves_board` rows in the canonical format):

- **Daily section writer** (`intel/daily.py` `write_section`) and **brief analyst** (`intel/brief.py` `write_brief`, via `desk.produce`): the INSTRUMENTS block for the theater. A series qualifies with strength 2 from distinctive tags the theater corroborates (its own account, or 2+ member headlines): 1 per shared distinctive tag, 2 when the tag names the series itself ("hormuz", "brent"). Distinctive = tag rarity at or above the catalog's median-mention idf, so generic tags ("risk", "energy") add weight but never qualify a series alone. Bounded to `MAX_INSTRUMENT_LINES`.
- **Daily summary writer** (`daily.write_summary`): series flagged unusual, or outside their full-history range unless merely trending (a two-sigma t-test on the last 90 days of changes: steady debt or yield climbs drop out, a collapse like Hormuz stays), across all series, whether or not a theater claims it.
- **Grounding**: public-display series' source URLs are primary evidence in `normalise_section` / `brief.normalise` (they may ground `researched` and key figures). `[internal source]` series inform the writer but their URLs are not offered as citable.
- **Refresh**: `newsroom intel daily` / `cycle` run `instruments.collect.collect()` first (best-effort; `--no-refresh` skips), reported as `sensing_refresh.instruments`.
