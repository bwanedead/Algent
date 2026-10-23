# Foundation: the operating envelope (2026-10-23)

Why this exists: in October we re-platformed twice under pressure (Supabase disk full → crash loop → egress overage → move to server + R2) and lost
data twice (two weeks of Pulse rationale; 42 daily chart files). Both were foreseeable. This page is the register of **every resource we depend on,
its limit, what we actually use, how it fails, and the guard**. Rule: **a new product or job must add its rows here before it ships**, and a guard must
exist for every limit we could plausibly hit within a year.

Companion docs: storage mechanics `database-budget.md`, site structure `information-architecture.md`, machine `../guides/worker-server.md`, accounts `../guides/accounts.md`.

**Status (2026-10-23): plan steps 1-5 are built (section 5); the server-side steps still need running once, in the order in "Operator checklist" below.**
Measured figures in the register are from 10-23 on the server; figures marked *expected* are derived from the code and are replaced by the first
`newsroom envelope` / `newsroom backup snapshot --dry-run` / `newsroom maritime compact-log` output.

## 1. Principles (the four questions every product answers)
1. **Tier.** Where does its data live? Pick one of: server store (the record) · R2 (publication) · nothing (derived, rebuildable).
   Nothing is stored only in a third-party service.
2. **Growth.** What is the steady-state size and the growth per day, measured? Every append-only file has a retention or a rollup, or it says why not.
3. **Backup.** Is it irreplaceable? If yes, it is in the nightly backup (tested by `tests/test_backup_coverage.py`) and restorable by a runbook we
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

## 3. Register of data on the server (measured 10-23; "now" = after steps 1-5)

| Store | Size | Written last 7 d | Irreplaceable? | Backed up | Growth control |
|---|---|---|---|---|---|
| `maritime_store/log.jsonl` | **1.7 GB** → *expected a few MB* after `compact-log --apply` | 1.7 GB (~250 k lines/day) → *expected < 1 MB/day* | no (nothing reads it) | no (daily summaries are) | **transitions only** (compact line per open/ended/unresolved, never "ongoing"), dedupe ledger + per-vessel cooldown, `LOG_KEEP_DAYS = 7`, then the daily summary (`database-budget.md`) |
| `library_store` | 123 MB (1 file) | 129 MB | no (crawl cache) | no | it is one **SQLite** file (page-level writes, `MAX_DB_BYTES` 400 MB retention), not a whole-file rewrite: nothing to change (see step 5) |
| `live_store` | 46 MB | 46 MB | no (relearns ~3 wk) | no | snapshots overwrite |
| `profile_store` | 34 MB | 5 MB | **yes: the corpus** | yes | append-only, small |
| `intel_store` (dailies, boards, drafts, **visuals/**) | 21 MB | 10 MB | **yes** | yes | ~1.4 MB/day + saved visuals ~0.3 MB/day |
| `actors_store` | 17 MB | 0 | refetchable | yes | — |
| `geoledger_store` | 17 MB | 16 MB | partly (status events = yes) | yes | already **append-only JSONL** (`assets.jsonl`, `events.jsonl`); the churn was the git mirror copying a changed file whole, now bounded by the 10 MB mirror threshold |
| `statements_store` | 15 MB | 7 MB | yes (extractions) | yes | — |
| `instruments_store`, `markets_store`, `sanctions_store`, `ai_benchmarks_store` | 9 / 8 / 7 / 3 MB | ~25 MB | partly (forward capture) | yes | rewrite churn, small |
| `pulse_store` | 2 MB | 0.5 MB | **yes** | yes | — |
| `/var/log/journal` | 562 MB | — | no | no | **capped at 200 MB** by `infra/server/journald-ohmega.conf` (installed by `install_schedules.sh`) |
| R2 `backups/daily/` (private bucket) | *expected 20-35 MB × ≤ 34* | one object a night | — | is the backup | 14 daily + 8 weekly + 12 monthly, `snapshot.plan_retention` |

Every row above has a budget in `ops/envelope_flags.py` and a line in `newsroom envelope`.

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
6. **Then features resume**: custom domain for R2 (production reads); Vercel usage check / plan decision; GPS jamming/attack log; the knowledge graph for agents.

## Operator checklist (server, in this order)
1. Deploy happens by push (the server pulls `organic-dev` every 5 min). Then `ssh` in.
2. `cd ~/Algent/backend && .venv/bin/python -m algent_backend.cli newsroom maritime compact-log` (dry run: lines, opens before / after per kind, bytes), then `... compact-log --apply`. Run it once; the stream service keeps appending safely.
3. Cloudflare: create a **private** R2 bucket (no public access); make sure the R2 API token has Object Read & Write on it. Add `R2_BACKUP_BUCKET=<name>` to `~/algent.env`.
4. `... newsroom backup snapshot --dry-run` (true size), then `... newsroom backup snapshot`, then `... newsroom backup restore-drill`. Check `~/ops-log.md`.
5. `~/Algent/infra/server/install_schedules.sh` (sudo: journald cap, and the new timers `backup-snapshot`, `backup-drill`, `envelope`).
6. `... newsroom envelope --text`; fix whatever is warn/fail (disk numbers, feeds, the unrecorded accounts).
7. For the lost charts: `... newsroom intel daily --date 2026-10-14 --rerender` first (free: re-sends anything saved, nothing is yet), then per date `--visuals-only --fresh-visuals` if you want them redrawn (paid, small).
