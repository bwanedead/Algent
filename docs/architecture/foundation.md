# Foundation: the operating envelope (2026-10-23)

Why this exists: in October we re-platformed twice under pressure (Supabase disk full → crash loop → egress overage → move to server + R2) and lost
data twice (two weeks of Pulse rationale; 42 daily chart files). Both were foreseeable. This page is the register of **every resource we depend on,
its limit, what we actually use, how it fails, and the guard**. Rule: **a product exists only if it is in the registry (section 3); a new product or job adds its entry there before it ships**, and a guard must
exist for every limit we could plausibly hit within a year.

Companion docs: storage mechanics `database-budget.md`, site structure `information-architecture.md`, machine `../guides/worker-server.md`, accounts `../guides/accounts.md`.

**Status (2026-10-23): plan steps 1-5 are built (section 5); the server-side steps still need running once, in the order in "Operator checklist" below.**
Measured figures in the register are from 10-23 on the server; figures marked *expected* are derived from the code and are replaced by the first
`newsroom envelope` / `newsroom backup snapshot --dry-run` / `newsroom maritime compact-log` output.

## 1. Principles (the four questions every product answers)
1. **Tier.** Where does its data live? Pick one of: server store (the record) · R2 (publication) · nothing (derived, rebuildable).
   Nothing is stored only in a third-party service.
2. **Growth.** What is the steady-state size and the growth per day, measured? Every append-only file has a retention or a rollup, or it says why not.
3. **Backup.** Is it irreplaceable? If yes, it is in the nightly backup (derived from the registry, tested by `tests/test_backup_coverage.py`) and restorable by a runbook we
   have actually run (`newsroom backup restore-drill`, monthly).
4. **Failure.** What does the reader see when its source or job fails? The site keeps the last good page and says it's stale. It never goes blank, and it
   never shows a cached error as truth.
5. **Local first.** Whatever is published is first written to a server store (`tests/test_local_first_publishing.py` fails on a new uploader that is not registered
   with its local copy).

## 2. Register of external dependencies

| Resource | Plan / limit | Our use (measured 10-23) | How it fails | Guard | Gap |
|---|---|---|---|---|---|
| **DigitalOcean droplet** (the record) | 2 vCPU, 4 GB RAM, 77 GB disk | 12 GB used; RAM ~1.4 GB + cache | disk full, OOM, host loss | `newsroom envelope` disk / RAM / journald rows (budgets `ops/envelope_flags.py`); nightly R2 snapshot; monthly restore drill | **closed once the first snapshot has run** (needs the private bucket, below); a whole-droplet DO snapshot is still not taken (the R2 snapshot restores the data, `worker-server.md` rebuilds the machine) |
| **Cloudflare R2** (publication + backups) | free: 10 GB, 1 M Class A, 10 M Class B / month; card on file | 69 MB; 4.3 k A month-to-date (0.6%); snapshots *expected* +0.7-1.2 GB and ~210 Class A / month | overage bills; r2.dev rate-limit | hard stop at 90%, warn 70% (`newsroom storage status`, envelope `r2` row); Cloudflare $1 budget alert; backups in a separate **private** bucket (`R2_BACKUP_BUCKET`) | r2.dev is "not for production" → custom domain + cache; the R2 token must cover the backup bucket |
| **Vercel** (site) | Hobby: bandwidth, function and ISR quotas, non-commercial terms | unmeasured | quota → throttled/blocked; build fails if data source fails | ISR keeps last good page; lean per-page docs; per-product revalidate | **no usage check; Hobby plan forbids commercial use** (open, step 6) |
| **GitHub `algent-data`** (second backup path) | git: 100 MB per file hard limit; repos >1 GB discouraged | 240 MB working copy, 7.9 MB pack | a file >100 MB fails the push; history grows with every rewritten JSON | **kept, but only files under 10 MB** (`data_backup/flags.MIRROR_MAX_FILE_BYTES` = limit / 10); bigger files are reported `too_big_for_git` and live in the R2 snapshot | the existing history stays (no rewrite); it is no longer the primary backup |
| **Model APIs** (paid) | our caps | daily runs ~$0.01–0.10 each logged | runaway spend | watchdog $15/run, $40/day halt; per-job caps; envelope `spend_day` / `spend_month` rows | spend figures look too low to trust; verify against the provider invoice |
| **SearXNG** (search) | self-hosted; upstream engines block datacenter IPs | ~570 searches/day, 100% free | engines blocked → thin results | engine probe + disabled list; envelope `search` row (warn < 8 results, fail at 0) | — |
| **aisstream / ADS-B / FIRMS / IODA / USGS / GIE** | free, keyless or free key | continuous | feed dies or changes format | per-feed freshness in doctor; envelope `feeds` row | anomaly "learning" until ~3 weeks of history |
| **Cloudflare / DO / GitHub / Vercel accounts** | — | — | one lost login = lost access | `../guides/accounts.md` inventory + quarterly recovery pass | the registrar and recovery locations are marked **unrecorded** in it; operator fills them in |
| **Supabase** | paused 10-22; delete after 90 days (~2027-01-20) | 0 | — | off by flags | delete when sure |

## 3. Register of products and their data (generated from the product registry)

**A product exists only if it is in the registry** (`backend/algent_backend/ops/products/registry.py`). One typed entry per product says where its data
lives, whether losing it is permanent, how its growth is bounded, how big it may get, which jobs run it and when, what it publishes and which pages read
it. Everything operational is *derived* from that entry instead of being told by hand in six places:

| Derived thing | From | Where it is read |
|---|---|---|
| nightly mirror to the data repo, R2 snapshot, restore, coverage | stores of `irreplaceable` products | `data_backup/sync.py::_sources()` -> `views.backup_sources()` |
| per-store size budgets and the `store:*` envelope rows | `Store.budget` | `ops/envelope.py` |
| every systemd timer (name, command, calendar) | `Product.jobs` | `newsroom products timers` -> `infra/server/install_schedules.sh`; `jobs.sh <job>` -> `newsroom products run <job>` |
| the unattended paid jobs | jobs with `spend="paid"` | `ops/schedule.py::jobs()` (kill switch, runner claim and spend halt unchanged) |
| retention / prune entry points | `Product.retention` (`ref`, `by`) | `ops/products/validate.py` (unbounded growth with no policy fails a test) |
| the table below | the registry | `newsroom products table --write` (a test fails when it drifts) |
| site routes and publications | `site_routes`, `publishes` | `sites/ohmega-monster/lib/products.json` (`newsroom products contract --write`); a test requires every page route to belong to a product |
| live-machine verdict | everything above | `newsroom products check`, embedded in `newsroom doctor` |

Adding a product: add its entry (stores with budgets and a reason for any store not backed up, a retention policy that names the code that applies it, jobs
or a `manual` note, routes, publications), then `newsroom products table --write` and `newsroom products contract --write`. Forgetting a place is no longer
possible: `tests/test_products_registry.py` and `tests/test_backup_coverage.py` fail first. Budgets marked "estimate" have no measurement yet: run
`newsroom envelope --text` on the server and replace them.

<!-- products:table:start (generated: `newsroom products table`) -->
| Product | Stores (steady → fail, MB) | Irreplaceable | Growth control | Jobs | Publishes | Pages |
|---|---|---|---|---|---|---|
| **Dailies (geopolitics, AI)** (`dailies`) | `intel_store` 21 → 1,500<br>`site_intel` 5 → 1,000 | **yes**: paid editorial work and published reports; the saved visuals exist only here (42 charts were lost when they were upload-only) | append-only: dailies, boards, drafts and visuals are the record; ~10 MB a week is 2.8 years of headroom at the fail line | `daily-1` 05:30 UTC (paid)<br>`daily-2` 17:30 UTC (paid)<br>`ai-daily` 09:00 UTC (paid) | `daily/`, `briefs/`, `snapshots/`, `theaters/`, `/analytics/daily/` | `/daily`, `/daily/[desk]`, `/daily/[desk]/[date]`, `/daily/[desk]/archive`, `/intel/briefs/[slug]`, `/intel/events/[date]/[theater]/[n]` |
| **Situations (living files)** (`situations`) | - | no: derived from the dailies (intel_store holds the source) | derived: rebuilt from the dailies on every daily run (theaters/<id>.json); clearing it loses nothing | manual: rebuilt on every daily run and by `newsroom publish`; no timer of its own | `theaters/` | `/situations`, `/situations/[id]`, `/intel/graph` |
| **Pulses (0-100 gauges)** (`pulses`) | `pulse_store` 2 → 200 | **yes**: two weeks of Pulse reasoning were lost once when it was missing from the backup | append-only: influences are never rewritten or removed; ~0.5 MB a week | manual: written by the daily runs (no timer of its own) | `pulses/` | `/pulses` |
| **Articles** (`articles`) | `draft_store` 5 → 500<br>`treatment_store` 5 → 500<br>`lead_store` 2 → 500<br>`site_articles` 10 → 1,000 | **yes**: paid editorial work (memory: never redo paid work) and the published articles | append-only: every draft, treatment and lead is kept (lineage to its profile); a few MB a week | manual: `newsroom run` by hand, irregular: an article is the operator's call | `articles/`, `docs/`, `/analytics/` | `/articles`, `/articles/[slug]` |
| **Research profiles (the corpus)** (`profiles`) | `profile_store` 34 → 1,500 | **yes**: the corpus: it cannot be re-bought cheaply and sixteen profiles were once silently overwritten | append-only: every save also writes _history/<id>/<rev>; nothing is overwritten or deleted | manual: written by article and daily research runs | - | - |
| **Menu (headlines) and run logs** (`menu`) | `runs_store` 200 → 4,000 (not backed up)<br>`site_radar` 2 → 500 | **yes**: the published menus exist nowhere else once the database is gone; the run logs themselves are expendable | prune: only the newest 5 runs are kept; older history stays in runs_index.jsonl | `menu` 05:00 UTC (paid) | `radar/` | `/daily/headlines`, `/daily/headlines/[slug]` |
| **Live feeds (ships, aircraft, quakes, fires, outages)** (`live`) | `live_store` 46 → 500 (not backed up) | no: re-collectable from public feeds | prune: hour files older than HOUR_KEEP_DAYS (60) are deleted; event snapshots are replaced each run | `live-ioda` `*:0/15`<br>`live-usgs` `*:0/10`<br>`live-adsb` `*:0/15`<br>`live-firms` `*-*-* 0/3:00:00`<br>`ais` always on | `live/` | `/live` |
| **Flows (ship lanes, grain, money)** (`flows`) | - | no: aggregates of the live stream, rebuilt as it runs | overwrite: tracker and days.json are bounded aggregates replaced atomically | `flows` `*:7/15` | `live/` | - |
| **Satellite (Sentinel-2 chips, night lights)** (`satellite`) | - | no: re-observed daily; the append-only records.jsonl is small and re-derivable from imagery | prune: dated chips are pruned to the KEEP_DATED (3) newest scenes per site plus the baseline | `satellite` `*-*-* 03:20` | `live/`, `/satellite/` | `/intel/satellite` |
| **Maritime behaviour** (`maritime`) | `maritime_store` 50 → 3,000 (not backed up)<br>`maritime_daily` 1 → 500 | **yes**: the daily summaries are the only long record of ship behaviour (backed up as maritime_daily) | rollup: daily ship summaries are written then the raw event log is cut to LOG_KEEP_DAYS (7) | `maritime-rollup` `*-*-* 04:05` | `maritime/` | `/intel/maritime` |
| **Sanctions** (`sanctions`) | `sanctions_store` 7 → 500 | **yes**: forward capture: the diff history of the lists cannot be re-fetched | append-only: events.jsonl is never rewritten; snapshots/<src>.json are replaced atomically | `sanctions` `2/6:25` | `sanctions/` | `/intel/sanctions` |
| **Calendar (look-ahead)** (`calendar`) | `calendar_store` 2 → 500 | **yes**: revision history (a moved or withdrawn date) cannot be re-fetched | append-only: items.jsonl keeps every revision; status.json is replaced | `calendar` `*-*-* 04:40` | `calendar/` | `/calendar` |
| **AI benchmarks** (`ai_benchmarks`) | `ai_benchmarks_store` 3 → 200 | **yes**: forward-captured Arena snapshots and lab claims cannot be re-fetched | append-only: results.jsonl is never edited; the catalog and status are replaced | `ai-bench` `0/12:55`<br>`ai-discovery` `*-*-* 06:50` (capped) | `data/ai-benchmarks.json` | `/intel/ai` |
| **Instruments (public data series)** (`instruments`) | `instruments_store` 9 → 500 | **yes**: forward capture of revisions and the live-feed daily counts (the baselines' history) | append-only: a fetch appends only a new or revised period; nothing is edited or removed | `instruments` `0/6:40` | `data/` | - |
| **Statements (on the record)** (`statements`) | `statements_store` 15 → 500 | **yes**: extractions are paid model work and the record is the product | append-only: statements.jsonl is append-only (ids dedupe); raw transcripts are internal and kept with it | `statements` `1/6:10` | `data/` | `/intel/record` |
| **Actors (state profiles)** (`actors`) | `actors_store` 17 → 500 | **yes**: refetchable but cheap to keep, and revisions are forward capture | append-only: a fetch appends only a never-seen or changed (country, year); no line is edited | manual: `newsroom actors fetch` by hand: indicators change yearly, no timer is needed | `actors/`, `data/actors/` | `/intel/actors`, `/intel/actors/[iso]` |
| **Geoledger (assets and status events)** (`geoledger`) | `geoledger_store` 17 → 500 | **yes**: status events are partly forward capture | append-only: assets/events/merges.jsonl are never rewritten; cache/overpass is keyed by query hash (overwritten, finite) | manual: `newsroom geo ...` seeds and updates by hand; nothing in it changes between operator actions | `geo/` | `/intel/places/[id]` |
| **Markets and the paper trader** (`markets`) | `markets_store` 8 → 500 | **yes**: our forecasts and trades are the scored record; they cannot be reconstructed | append-only: history is never rewritten so the record cannot be quietly improved; ~2 MB a week estimated | `markets` `3/4:50`<br>`markets-daily` 07:30 UTC (paid) | `data/track-record.json` | `/intel/forecasts`, `/intel/track-record` |
| **Source library (crawl cache)** (`library`) | `library_store` 123 → 1,000 (not backed up) | no: re-crawled by the timer (about a day to refill) | prune: enforce_retention drops the oldest pages past MAX_DB_BYTES (400 MB), news before analysis before primary | `library` `0/4:20` | - | - |
| **Corpus index (queryable view of the record)** (`corpus_index`) | `corpus_store` 75 → 1,500 (not backed up) | no: derived: every row comes from another product's store; deleting it loses nothing | derived: rebuilt from the record; --full builds a fresh compact file, incremental builds VACUUM past 25% free pages | `corpus-build` `2/4:25` | - | - |
| **Agent feeds and API** (`agent_feeds`) | `site_data` 10 → 1,000 | **yes**: what was published exists nowhere else once the database is gone (the served copy is the only copy of the documents) | derived: built from the dailies, profiles and Pulses on publish; the bucket holds the served copy | manual: rebuilt on every publish by the daily and article runs | `data/`, `feeds/` | `/developers` |
| **Site hubs and surfaces** (`site`) | - | no: reads the other products' published documents | derived: presentation only; no data of its own | - | - | `/`, `/data`, `/globe`, `/lab/scene` |
| **Operations (deploy, watchdog, envelope, housekeeping)** (`ops`) | - | no: code and logs only; ~/ops-log.md grows by a few lines a day | prune: housekeeping deletes fetch-cache files past their TTL and per-job run logs older than 30 days | `update` `*:0/5`<br>`watchdog` `*:0/2`<br>`envelope` `*-*-* 07:10`<br>`housekeeping` `*-*-* 03:55` | - | - |
| **Backups** (`backup`) | - | no: it is the backup (state in backup_state.json, objects in the private R2 bucket) | prune: snapshots are thinned to 14 daily + 8 weekly + 12 monthly | `backup` `*-*-* 06:15`<br>`backup-snapshot` `*-*-* 06:40`<br>`backup-drill` `*-*-01 07:30:00` | - | - |
| **Legacy Postgres tables** (`database`) | - | no: publication moved to the server and R2 (Supabase paused 10-22) | prune: retention windows on the growing tables + VACUUM | `db-prune` `*-*-* 03:40` | - | - |
| **Caches and scratch** (`caches`) | `fetch_cache` 50 → 2,000 (not backed up)<br>`retrieval_store` 5 → 2,000 (not backed up)<br>`ingestion_store` 0 → 8,000 (not backed up) | no: every store here is rebuilt on demand | prune: fetch cache entries past the 6 h TTL are deleted daily; ingestion raw batches are pruned by the CLI | manual: refilled on demand; expired by the ops housekeeping job | - | - |
<!-- products:table:end -->

Not products (resources, see section 2): `/var/log/journal` (562 MB, **capped at 200 MB** by `infra/server/journald-ohmega.conf`, installed by `install_schedules.sh`);
R2 `backups/daily/` in the private bucket (*expected 20-35 MB x <= 34*: 14 daily + 8 weekly + 12 monthly, `snapshot.plan_retention`).
Measured 10-23 (server): `library_store` 123 MB is one SQLite file (page-level writes, `MAX_DB_BYTES` 400 MB); the 1.7 GB `maritime_store/log.jsonl` was the incident
(transitions only now, `LOG_KEEP_DAYS = 7`, then the daily summary: `database-budget.md`); `geoledger_store` is already append-only JSONL (its 16 MB "written" was the mirror
copying a changed file whole, now bounded by the 10 MB mirror threshold). Every store row above has a budget in the registry and a line in `newsroom envelope`.

## 4. Risks, ranked (state after steps 1-5)
1. **The maritime log was the next disk incident.** Fixed in code (transitions only, dedupe, 7 days). *Still to run:* `newsroom maritime compact-log --apply` to shrink the existing 1.7 GB.
2. **Backups lived in a git repo of rewritten JSON.** Primary is now an R2 snapshot with a verified manifest; git mirror is capped at 10 MB files. *Still to do:* create the private bucket, set `R2_BACKUP_BUCKET`, take the first snapshot, run the first drill.
3. **The droplet is the only copy of the record** until the first snapshot exists; after it, a host failure means rebuild plus `newsroom backup restore` (the drill proves this monthly).
4. **Vercel Hobby is unmeasured.** Open (step 6).
5. **Published-only artifacts.** Closed for the daily visuals (`visuals_store`, registry test). The 42 charts of 10-14 to 10-21 **cannot be regenerated without a model**: their specs were only ever uploaded (the draft archive holds section drafts, not visual specs). `intel daily --date D --visuals-only --fresh-visuals` redraws them (one planning call plus one structured call per visual, cents each; harness charts also need the harness).
6. **journald uncapped.** Drop-in written; needs `install_schedules.sh` (sudo) once.
7. **No restore drill, no account inventory.** Both exist now (`restore-drill`, `accounts.md`); the inventory has unrecorded cells only the operator can fill.

## 5. The plan (in order; each step lands with a test or a doctor line)
1. **Maritime log → transitions only. DONE.** `maritime/eventlog.py`: one compact line per open / ended / unresolved (`id, kind, state, mmsi, imo, name, ship_class, at, lat, lon, area, confidence`), never "ongoing", never the full object.
   Cause of the ~100 k opens/day: events evicted by the `EVENTS_MAX` cap were re-found by their detector each pass and re-logged `open`, and the sanctioned detector's ongoing/ended flapping was logged each flip. Fixed by a ledger (one open + one terminal per id) and a per-vessel+kind cooldown derived from each detector's own minimum duration (`flags.LOG_COOLDOWN_S`), and by `store.upsert` not re-adding closed events or evicting going ones.
   `LOG_KEEP_DAYS = 7`. One-shot `newsroom maritime compact-log [--apply]` converts the legacy file (drops ongoing and repeats, reports opens before/after per kind), summarises complete days, cuts to 7 days. Tests: `test_maritime_detect.py`, `test_maritime_rollup.py`.
2. **Backups → R2 snapshots. DONE.** `data_backup/snapshot.py`, `newsroom backup snapshot|status|prune|restore-drill|restore`; manifest with per-file sha256; 14/8/12 retention through the R2 meter; private bucket `R2_BACKUP_BUCKET`; timers `backup-snapshot` (06:40) and `backup-drill` (monthly) and the drill result in `~/ops-log.md` + `backup_state.json`. **Decision on the git mirror: kept**, as a cheap second vendor path, but it skips files over 10 MB (a tenth of GitHub's 100 MB limit) so rewritten-large files no longer churn its history. Test: `test_backup_snapshot.py`.
3. **Local-first publishing. DONE for the daily visuals; registry for the rest.** `visuals_store.local_first` wraps every producer's uploader (`intel_store/visuals/<domain>/<date>/`, backed up; no upload if the local write fails). `intel daily --date D --rerender` now also re-sends a record's saved visuals, rebuilding native stills from saved specs with no model (and it no longer drops sections' `visuals`). Regenerable free: **native forms (timeline, mapstory, network, flow, tracker_compare) and scene3d from now on** (spec + still are saved; still re-drawn from the spec); chart-harness SVG/PNGs re-upload from saved bytes only. **Not regenerable free: anything published before this change**, including 10-14 → 10-21; the command names each such visual and the paid repair. Test: `test_local_first_publishing.py` (AST registry of every module that reaches the object store, with its local copy).
4. **Doctor = the envelope. DONE.** `newsroom envelope [--log] [--text]`: disk, RAM, journald, each store (size + 7-day writes), R2 month-to-date, backup age, last restore drill, feed freshness, search results, spend today/month, each ok/warn/fail against `ops/envelope_flags.py` (every budget has its reason in a comment). `newsroom doctor` embeds the rows it lacked (`envelope:*`). Daily timer `envelope` (07:10) logs one line to `~/ops-log.md`. Test: `test_envelope.py`.
5. **Small fixes. DONE.**
   - journald: `infra/server/journald-ohmega.conf` (`SystemMaxUse=200M`), installed by `install_schedules.sh` (needs sudo); one-liner in the file header.
   - `library_store` and `geoledger_store`: **no change needed, on purpose.** The library is a single SQLite file (page-level writes; the 129 MB "written" is its mtime), and the geoledger is already append-only JSONL. Splitting either would add code for no saving. What actually churned was the git mirror copying changed files whole; the 10 MB threshold fixes that. The envelope's "written 7 d" column will show if either ever really rewrites.
   - `docs/guides/accounts.md`: the inventory (names only), with the cells only the operator can know marked **unrecorded**.
6. **Then features resume**: custom domain for R2 (production reads); Vercel usage check / plan decision; GPS jamming/attack log; the knowledge graph for agents (Phase A built: the `corpus_index` product, `corpus-index.md`; server views and agent endpoints next).

## Operator checklist (server, in this order)
1. Deploy happens by push (the server pulls `organic-dev` every 5 min). Then `ssh` in.
2. `cd ~/Algent/backend && .venv/bin/python -m algent_backend.cli newsroom maritime compact-log` (dry run: lines, opens before / after per kind, bytes), then `... compact-log --apply`. Run it once; the stream service keeps appending safely.
3. Cloudflare: create a **private** R2 bucket (no public access); make sure the R2 API token has Object Read & Write on it. Add `R2_BACKUP_BUCKET=<name>` to `~/algent.env`.
4. `... newsroom backup snapshot --dry-run` (true size), then `... newsroom backup snapshot`, then `... newsroom backup restore-drill`. Check `~/ops-log.md`.
5. `~/Algent/infra/server/install_schedules.sh` (sudo: journald cap, and the new timers `backup-snapshot`, `backup-drill`, `envelope`).
6. `... newsroom envelope --text`; fix whatever is warn/fail (disk numbers, feeds, the unrecorded accounts).
7. For the lost charts: `... newsroom intel daily --date 2026-10-14 --rerender` first (free: re-sends anything saved, nothing is yet), then per date `--visuals-only --fresh-visuals` if you want them redrawn (paid, small).

## 6. Threats not yet covered (operator review, 2026-10-23)
Ranked by likelihood × damage. Each needs a guard or a written decision to accept it.

| # | Threat | What happens | Guard to add |
|---|---|---|---|
| 1 | **Secrets have one copy** (`~/algent.env` on the droplet) | Server loss means every key is regenerated by hand, across many accounts | Keys in a password manager (operator); `docs/guides/accounts.md` lists every key name and where to regenerate it |
| 2 | **Domain / card / account lapse** | Registrar renewal or an expired card silently kills the site or R2 | Record renewal dates and card expiry in the accounts doc; calendar reminders |
| 3 | **Server rebuild is untested** | Backups exist but nobody has rebuilt a box from zero | A written, once-tested rebuild runbook (droplet → repo → env → restore snapshot → install_schedules → SearXNG) |
| 4 | **Readers we invite: AI agents and scrapers** | Heavy `/api/v1` + MCP + page reads push Vercel bandwidth and functions, or R2 Class B | Custom domain + Cloudflare cache in front of R2; rate limit on `/api/v1` and `/api/mcp` (the `middleware.ts` seam); budget in the envelope |
| 5 | **Vercel Hobby terms and limits** | Commercial use is not allowed on Hobby; quotas are unmeasured | Decide before monetising: Vercel Pro, or a static export on Cloudflare Pages (free, commercial OK) |
| 6 | **Model/provider drift** | A model is retired or repriced, a key is revoked, or spend tracking under-counts | Monthly reconciliation of tracked spend against provider bills; model ids in flags with a fallback; the doctor checks each harness |
| 7 | **Free data feeds die or change terms** | aisstream, adsb.lol, OpenSky, FIRMS, search engines or Comtrade go away or block us | Per-feed freshness already alerts; record each source's licence/ToS and attribution duty in one table |
| 8 | **Content and legal risk** | Auto-published AI journalism makes a false claim about a real person or company | Corrections ledger + kill switch (exist); a publish floor for named-person claims; a visible corrections page |
| 9 | **Corpus quality drift** | Errors compound in the profile and claim corpus, which is the asset | Contradiction checks on new claims vs existing; periodic sampled audits; provenance on every claim (exists) |
| 10 | **Front-end has no local checks** | Only Vercel's build type-checks the site; there are no UI tests, and a bad merge reaches preview first | `node_modules` installed once by the maintainer + `tsc`/lint in the merge routine; smoke-test script over key routes after each deploy |
| 11 | **Public repo** | A secret or unpublished corpus committed by mistake is world-readable | Pre-commit secret scan; corpus paths in `.gitignore` (exist); never `git add -A` blindly |
| 12 | **Server maintenance** | OS security updates, reboots and Python deps age; a reboot mid-run kills a paid job | Monthly patch window outside the paid-job hours; services restart on boot (systemd, exists) |
| 13 | **Dev throughput** | The Claude usage limits stall builders mid-work | One builder at a time; builders commit WIP often (no lost work) |
