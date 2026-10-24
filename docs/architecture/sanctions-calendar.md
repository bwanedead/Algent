# Sanctions feed and forward calendar

Two free, model-free collectors that publish to the site (migration `012_sanctions_calendar.sql`). Code: `backend/algent_backend/sanctions/` and `backend/algent_backend/lookahead/`; CLI: `newsroom sanctions ...`, `newsroom calendar ...`; timers: `ohmega-sanctions` (every 6 h), `ohmega-calendar` (daily 04:40 UTC) in `infra/server/install_schedules.sh`; doctor checks `sanctions` and `calendar`.

## Sanctions designations

| Source | URL | Terms |
|--------|-----|-------|
| US Treasury OFAC, SDN list | `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML` | US government work, public domain. The host's TLS chain ends in a Treasury root that certifi lacks, so the download verifies against the OS store (`polite_http.download(system_trust=True)`). |
| UK Sanctions List (FCDO; replaced the OFSI consolidated list) | `https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.xml` | Open Government Licence v3.0. |
| EU consolidated financial sanctions list | `https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw` | Commission FSF; the token is the anonymous one the Commission documents. Free reuse with attribution (Decision 2011/833/EU). |

How it works: download, parse (streamed), diff against the stored snapshot (`diff.py`), append events (`events.jsonl`, deterministic ids), replace the snapshot, publish compact rows. OFAC dates nothing, so its first snapshot is only a baseline; UK and EU date their own designations, so their first run reports the last 30 days (`baseline=true`). A snapshot under 60% of the previous size is refused (truncated download). Designated vessels become geoledger assets (type `vessel`, id by IMO) with a `designated` status event by the publisher.

## Calendar

One module per source in `lookahead/sources/`, each a pure `parse(...)` tested on a saved fragment (`tests/test_calendar_sources.py`, `tests/test_lookahead.py`) and a `fetch(today)` that returns only items inside the window. Grade = `official` (the body's own schedule), `announced` (compiled or company-confirmed), `estimated` (generated from a published rule, or a projection) or `unconfirmed` (our own reading). The old three-level `confidence` stays for existing readers (high / medium / low).

| Source key | Kind | Where | Grade | Live count 2026-10-24 |
|---|---|---|---|---|
| `fed`, `ecb`, `boe` | central_bank | federalreserve.gov FOMC page; ecb.europa.eu Governing Council calendar; bankofengland.co.uk MPC dates | official | 4, 4, 3 |
| `boj` | central_bank | boj.or.jp meeting table (decision = second day) | official | 4 |
| `rba` | central_bank | rba.gov.au Board meeting schedules | official | 4 |
| `norges` | central_bank | norges-bank.no calendar (JSON embedded in the page) | official | 2 |
| `pboc` | central_bank | rule: Loan Prime Rate on the 20th, next day if a weekend (China holidays not modelled) | estimated | 6 |
| `bea` | data_release | bea.gov/news/schedule: GDP (advance, second, third) and Personal Income and Outlays (PCE) only | official | 6 |
| `bls_jobs` | data_release | rule: third Friday after the reference week (the one holding the 12th); bls.gov answers 403 | estimated | 6 |
| `wasde` | commodity_report | usda.gov WASDE page (yearly sentence of dates) | official | 6 |
| `eia_petroleum`, `eia_gas` | commodity_report | rule (Wednesday / Thursday weekly) plus the holiday exceptions on eia.gov/petroleum/supply/weekly/schedule.php and ir.eia.gov/ngs/schedule.html | announced, routine | 26, 26 |
| `opec` | opec | opec.org press releases ("the next meeting ... is scheduled for ...") | announced | blocked (HTTP 403) from the dev machine on 10-24 |
| `elections` | election, vote | `https://en.wikipedia.org/wiki/<year>_national_electoral_calendar` (wikitext, `action=raw`); referendums, plebiscites and initiatives are kind `vote`, runoffs stay elections ("(2nd round)") | announced (volunteer-compiled; CC BY-SA, facts only) | 24 |
| `unsc` | security_council | main.un.org programme of work (meetings) | official when readable; the site sits behind a bot challenge that sometimes answers an empty 202, reported as unavailable (never worked around) | 2 |
| `unsc_presidency` | security_council | main.un.org presidency table: who holds each month | official | 6 |
| `icj` | court | icj-cij.org press-release titles ("Public hearings to be held from ...", "Delivery of the Judgment on ...") | official; may legitimately be empty | 0 (no hearing announced; the August-September ones are past) |
| `summits` | summit | Wikipedia infobox dates for a curated list of page titles (G20 Miami, COP31, APEC China, CHOGM, BRICS, G7, NATO ...); a missing page is skipped, a redirect is never followed | announced | 4 |
| `ai_act` | regulation | artificialintelligenceact.eu implementation timeline | announced | 2 |
| `gtc` | conference | nvidia.com/gtc meta description ("GTC San Jose 2027 is coming March 15-18") | announced | 1 |
| `earnings` | earnings | Nasdaq public earnings calendar JSON, one request per weekday for 40 weekdays, filtered to NVDA, MSFT, GOOGL, META, AMZN, AAPL, TSM, ASML; beyond 30 days a projection | announced / estimated | 5 |
| `launches` | launch | Launch Library 2 (`ll.thespacedevs.com`, free tier, one request); notable only: crewed, planetary/deep space, heavy or new vehicles | announced when Go and day-precise, else estimated | 26 |
| `markets` | market_resolves | our markets store: every open mirrored market on its end date, linked to /intel/track-record; countries and theaters are those it was mapped to | estimated (`ohmega_derived`) | 0 on the dev machine (no store) |
| `watches` | deadline | open Pulse watches with a `horizon` date, linked to their situation (`situations`) | unconfirmed (`ohmega_derived`) | 0 on the dev machine |
| `corpus` | deadline, vote, summit | `lookahead/extract.py`: sentences of our dailies with a trigger word and an explicit date | unconfirmed (`ohmega_derived`) | (daily-driven) |

**Tried and skipped** (no key-free machine-readable schedule reachable with a plain client): Bank of Canada, SNB (past decisions only), Riksbank, Reserve Bank of India, CBRT, Banxico, BCB Copom and SARB (script-rendered pages, or the host refuses the connection); US BLS CPI (403 on every page and the ICS; the jobs report is the rule above), Eurostat release calendar and China NBS (script-rendered or no calendar page), OPEC MOMR and IEA OMR (403), IAEA Board of Governors, EU Council, NATO, WTO and UNGA calendars (403, 404 or script-rendered), ICC (no hearing list in the page), Google I/O, WWDC, Microsoft Build, NeurIPS, OpenAI DevDay (dates not machine-readable, or 403), and the investor-relations pages of NVIDIA, TSMC and ASML (403; Nasdaq's calendar stands in for earnings). Sanctions and treaty expiries are not in the calendar because neither store records an expiry date. When one of these gains a fetchable form, add a module and a `FETCHERS` entry (`lookahead/collect.py`).

**Merge, rank, window.** `merge.py` dedupes across sources at publish time: same kind family, overlapping days, title overlap coefficient >= 0.6 on non-filler words, intersecting countries when both name any; the most trusted item survives, absorbs the others' countries, theaters and situations and lists every source in `sources`. Items of one source never merge (two Fed meetings a week apart are two meetings) and the weekly EIA reports are never compared. `rank.py` gives each item an `importance` of 1 (routine), 2 (notable) or 3 (major) from its kind (G7/G20/NATO/COP summits, the big-eight central banks, GDP/PCE/jobs releases, presidential or general elections and referendums, ICJ judgments are 3; the weekly EIA reports, UN Security Council meetings and a market resolving are 1), +1 (cap 3) when linked to one of the five hottest theaters on the latest desk board, and capped at 2 when unconfirmed. The window is **14 days back** (what just happened) and **180 days ahead** (about two central-bank cycles and one summit season; further out a date is an announcement nobody has confirmed). `topic` (economy, central_banks, elections, diplomacy, security, energy, tech, space, markets) is derived from the kind (`TOPIC_OF`).

**Contract.** `ohmega.calendar` stays major 1: the new kinds and the fields `topic`, `importance`, `grade`, `situations` and `sources` are additive (the site normalises rows written before them: `norm` in `lib/calendar-shared.ts`). Documents: `calendar/next.json` (all active items in the window, ~85 KB for 160 items; ~250 KB expected once markets and watches are in) and `calendar/country/<ISO>.json` (that country's rows). The object store skips a document whose hash is unchanged, so an unchanged day writes nothing. The legacy Postgres table (migration 012) keeps only the original seven kinds its check constraint allows.

**Scheduling.** Two job classes in the registry (collector priority): `calendar` daily 04:40 UTC (`--group schedules`, every official calendar) and `calendar-fast` every six hours (`--group fast`: earnings, launches, our markets and watches, whose dates move or appear during the day). `newsroom calendar refresh [--source S ...] [--group schedules|fast]`.

A source that returns nothing never withdraws its items (except `icj`, `markets` and `watches`, whose honest answer is sometimes nothing); an item a healthy source stops listing becomes `active=false` (history stays). Extraction is mechanical: a sentence needs a trigger word (deadline, expires, vote, summit ...) AND an explicit future date; relative dates are ignored. The daily's sensing adds a `COMING UP` block (next 14 days; notable items naming the theater or touching a country it stands behind) and cites official pages only, never our own earlier reports.

## Site and API

`/calendar`: an "On the horizon, next 72 hours" strip, then week (default), month and list views over the whole window; topic chips, a country filter, a situation filter and a switch for routine items; each item shows its kind, importance (three bars), grade in words, every source as a link and its country and situation links (list view; flags in the grids). On a phone the grids become an agenda. Home's "Coming up", the globe HUD's "Coming up" panel, each theater's daily section and actor pages read the same document, notable items only (`importance >= 2` is applied in `views/home.py`, `views/hud.py` and `views/country.py`). `/intel/sanctions` (per-country strip with sparklines over a filterable table of events). API: `/api/v1/calendar` (`kind`, `topic`, `country`, `situation`, `grade`, `confidence`, `min_importance`, `routine`, `days` up to 180; rows carry `topic`, `importance`, `grade`, `situation_ids`, `sources`), `/api/v1/sanctions`; MCP tools `get_calendar`, `get_sanctions`. Apply migration 012 before deploying the site build.
