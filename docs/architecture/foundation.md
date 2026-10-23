# Foundation: the operating envelope (2026-10-23)

Why this exists: in October we re-platformed twice under pressure (Supabase disk full → crash loop → egress overage → move to server + R2) and lost
data twice (two weeks of Pulse rationale; 42 daily chart files). Both were foreseeable. This page is the register of **every resource we depend on,
its limit, what we actually use, how it fails, and the guard**. Rule: **a new product or job must add its rows here before it ships**, and a guard must
exist for every limit we could plausibly hit within a year.

Companion docs: storage mechanics `database-budget.md`, site structure `information-architecture.md`, machine `../guides/worker-server.md`.

## 1. Principles (the four questions every product answers)
1. **Tier.** Where does its data live? Pick one of: server store (the record) · R2 (publication) · nothing (derived, rebuildable).
   Nothing is stored only in a third-party service.
2. **Growth.** What is the steady-state size and the growth per day, measured? Every append-only file has a retention or a rollup, or it says why not.
3. **Backup.** Is it irreplaceable? If yes, it is in the nightly backup (tested by `tests/test_backup_coverage.py`) and restorable by a runbook we
   have actually run.
4. **Failure.** What does the reader see when its source or job fails? The site keeps the last good page and says it's stale. It never goes blank, and it
   never shows a cached error as truth.

## 2. Register of external dependencies

| Resource | Plan / limit | Our use (measured 10-23) | How it fails | Guard | Gap |
|---|---|---|---|---|---|
| **DigitalOcean droplet** (the record) | 2 vCPU, 4 GB RAM, 77 GB disk | 12 GB used; RAM ~1.4 GB + cache | disk full, OOM, host loss = **single copy of everything** | doctor disk/RAM lines; nightly backup | **no off-host snapshot of the whole box; backup goes to git (see below)** |
| **Cloudflare R2** (publication) | free: 10 GB, 1 M Class A, 10 M Class B / month; card on file | 69 MB; 4.3 k A month-to-date (0.6%) | overage bills; r2.dev rate-limit | hard stop at 90%, warn 70% (`newsroom storage status`); Cloudflare $1 budget alert | r2.dev is "not for production" → custom domain + cache |
| **Vercel** (site) | Hobby: bandwidth, function and ISR quotas, non-commercial terms | unmeasured | quota → throttled/blocked; build fails if data source fails | ISR keeps last good page; lean per-page docs; per-product revalidate | **no usage check; Hobby plan forbids commercial use** |
| **GitHub `algent-data`** (backup) | git: 100 MB per file hard limit; repos >1 GB discouraged | 240 MB working copy, 7.9 MB pack | a file >100 MB fails the push; history grows with every rewritten JSON | coverage test | **wrong tool for growing JSON; no restore drill** |
| **Model APIs** (paid) | our caps | daily runs ~$0.01–0.10 each logged | runaway spend | watchdog $15/run, $40/day halt; per-job caps | spend figures look too low to trust; verify |
| **SearXNG** (search) | self-hosted; upstream engines block datacenter IPs | ~570 searches/day, 100% free | engines blocked → thin results | engine probe + disabled list | no alert when result counts drop |
| **aisstream / ADS-B / FIRMS / IODA / USGS / GIE** | free, keyless or free key | continuous | feed dies or changes format | per-feed freshness in doctor | anomaly "learning" until ~3 weeks of history |
| **Cloudflare / DO / GitHub / Vercel accounts** | — | — | one lost login = lost access | — | **no written account inventory or recovery codes check** |
| **Supabase** | paused 10-22; delete after 90 days | 0 | — | off by flags | delete when sure |

## 3. Register of data on the server (measured 10-23)

| Store | Size | Written last 7 d | Irreplaceable? | Backed up | Growth control |
|---|---|---|---|---|---|
| `maritime_store/log.jsonl` | **1.7 GB** | **1.7 GB (~250 k lines/day)** | no (nothing reads it) | no (daily summaries are) | **rollup keeps 30 days = ~9 GB. Wrong: must log transitions only and keep days, not weeks** |
| `library_store` | 123 MB (1 file) | 129 MB (rewritten whole) | no (crawl cache) | no | bounded by crawl size; whole-file rewrite is churn |
| `live_store` | 46 MB | 46 MB | no (relearns ~3 wk) | no | snapshots overwrite |
| `profile_store` | 34 MB | 5 MB | **yes: the corpus** | yes | append-only, small |
| `intel_store` (dailies, boards, drafts) | 21 MB | 10 MB | **yes** | yes | ~1.4 MB/day |
| `actors_store` | 17 MB | 0 | refetchable | yes | — |
| `geoledger_store` | 17 MB | 16 MB (rewritten) | partly (status events = yes) | yes | rewrite churn bloats git history |
| `statements_store` | 15 MB | 7 MB | yes (extractions) | yes | — |
| `instruments_store`, `markets_store`, `sanctions_store`, `ai_benchmarks_store` | 9 / 8 / 7 / 3 MB | ~25 MB | partly (forward capture) | yes | rewrite churn |
| `pulse_store` | 2 MB | 0.5 MB | **yes** | yes (since 10-22) | — |
| `/var/log/journal` | 562 MB | — | no | no | **uncapped** |

## 4. Risks, ranked (what will bite next if we do nothing)
1. **The maritime log is the next disk incident.** ~290 MB/day of full event objects re-logged on every state touch ("ongoing" ×700/3000 lines).
   It's harmless today (65 GB free), but it is exactly the "record every micro event" pattern we said we'd stop.
2. **Backups live in a git repo of rewritten JSON.** History grows forever, single files approach the 100 MB limit, and we have never restored from it.
3. **The droplet is the only copy of the record.** No whole-machine snapshot; a host failure means rebuild plus git restore, untested.
4. **Vercel Hobby is unmeasured.** Bandwidth and ISR quotas are unknown, and its terms exclude commercial use, which matters before monetisation.
5. **Published-only artifacts.** Anything generated and uploaded without a server copy (that's how the 42 charts were lost). Rule: write locally first, publish second.
6. **journald uncapped** (562 MB and growing).
7. **No restore drill, no account inventory.** We find out what's missing only when it's needed.

## 5. The plan (in order; each step lands with a test or a doctor line)
1. **Maritime log → transitions only.** One compact line per open/close (id, kind, mmsi, at, lat/lon, confidence), never the full object, never
   "ongoing". Keep 7 days raw, then the daily summary. Truncate the existing 1.7 GB to 7 days after summarising.
2. **Backups → R2 snapshots, not git.** Nightly `tar.zst` of the irreplaceable stores to `backups/` in R2 (daily ×14, weekly ×8, monthly ×12),
   inside the R2 budget guard. The git mirror is kept only for small, human-diffable files, or retired. Add a **restore drill** command that restores
   to a temp dir and verifies counts. Run it monthly via a timer that logs the result.
3. **Local-first publishing.** Every publisher writes the artifact to a server store before uploading, and a test asserts it (no upload-only paths).
   Re-render the lost daily charts from drafts where possible.
4. **Doctor = the envelope.** One `newsroom envelope` command (and a doctor section) prints every register row: disk, RAM, journal, each store's size
   and 7-day growth against its budget, R2 month-to-date, backup age plus last restore drill, feed freshness, search health, spend. Each line is
   ok/warn/fail against a budget in flags. Logged daily to `~/ops-log.md`.
5. **Small fixes:** cap journald (`SystemMaxUse=200M`); stop rewriting `library_store` and `geoledger_store` whole (append or split); write an account
   inventory doc (which accounts exist and where recovery lives; no secrets).
6. **Then features resume**: custom domain for R2 (production reads); GPS jamming/attack log; the knowledge graph for agents.
