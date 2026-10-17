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

| Source | URL | Confidence |
|--------|-----|------------|
| Fed FOMC meetings | `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm` | high (official) |
| ECB Governing Council | `https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html` | high (official) |
| Bank of England MPC | `https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates` | high (official) |
| National elections | `https://en.wikipedia.org/wiki/<year>_national_electoral_calendar` (wikitext, `action=raw`) | medium (volunteer-compiled; CC BY-SA, facts only) |
| UN Security Council programme of work | `https://main.un.org/securitycouncil/en/content/programme-work` | high when readable; the site is behind a bot-challenge firewall that sometimes answers an empty 202, reported as unavailable (never worked around) |
| OPEC+ meetings | `https://www.opec.org/` press releases ("the next meeting ... is scheduled for ...") | medium |
| Our own daily reports | `lookahead/extract.py` | low (`ohmega_derived`) |

A source that returns nothing never withdraws its items; an item a healthy source stops listing becomes `active=false` (history stays). Extraction is mechanical: a sentence needs a trigger word (deadline, expires, vote, summit ...) AND an explicit future date; relative dates are ignored. The daily's sensing adds a `COMING UP` block (next 14 days; items naming the theater or touching a country it stands behind) and cites official pages only, never our own earlier reports.

## Site and API

`/calendar` (30-day density strip, Monday-first week grid, filters by kind and country; an agenda on a phone), `/intel/sanctions` (per-country strip with sparklines over a filterable table of events), a "Coming up" strip on Home and in each theater's daily section (the rows the writer was shown are stored on the section as `coming_up`, so an archived report keeps its day), and "Sanctions activity" and "Upcoming" sections on actor pages. API: `/api/v1/calendar`, `/api/v1/sanctions`; MCP tools `get_calendar`, `get_sanctions`. Apply migration 012 before deploying the site build.
