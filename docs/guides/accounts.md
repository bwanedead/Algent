# Accounts: what exists, what each holds, where recovery lives

The inventory the register in `../architecture/foundation.md` said was missing: one lost login must not mean lost access to the record, the money or the
site. **Names and purposes only. No passwords, keys, tokens, recovery codes or 2FA seeds are written here, ever.** Key *names* and what reads them are in
`../credentials.md`; the machine is described in `worker-server.md`.

How to read the "Recovery" column: it says *where the way back in is kept*, never the secret itself. Where the repo cannot know (a registrar, a password
manager, a phone), the cell says **unrecorded**; the operator fills those in once and then they are checked in the quarterly pass below.

## Infrastructure accounts (losing one stops the system or loses data)

| Account | Holds | Plan / money | Access we use | Recovery lives |
|---|---|---|---|---|
| **DigitalOcean** | the droplet `ohmega-server` (TOR1, 2 vCPU / 4 GB / 77 GB): **the only copy of the record** until the R2 snapshots exist (`../architecture/foundation.md`) | $24/month, card | SSH only: operator key + automation key `~/.ssh/ohmega_ops`; root login and passwords are off | account 2FA and billing e-mail: **unrecorded**. Rebuild from nothing: `worker-server.md` "Rebuild from nothing" plus the latest R2 snapshot (`newsroom backup restore`) |
| **Cloudflare** | R2 buckets: `ohmega` (public publication, `pub-….r2.dev`) and the **private backup bucket** (`R2_BACKUP_BUCKET`, snapshots under `backups/daily/`); the R2 API token(s); later the `data.` custom domain / DNS | free tier, **card on file** (overage bills), $1 budget alert | worker env `R2_*` only; the token is bucket-scoped write access | account 2FA: **unrecorded**. The data in the publication bucket is rebuildable (`newsroom publish rebuild-all`); the backup bucket is not rebuildable, so the account is a second single point: keep its recovery codes off the droplet |
| **GitHub** | repos `Algent` (code; `organic-dev` working branch, `site-live` publish branch) and `algent-data` (private; git mirror of small files, runner claim); two **deploy keys** (one per repo) on the droplet | free | deploy keys for the server; the operator's own login for everything else | account 2FA and recovery codes: **unrecorded**. If the droplet is lost the deploy keys are re-created (`worker-server.md` "Access it holds") |
| **Vercel** | the site project (root `sites/ohmega-monster`, production branch `site-live`), env `NEXT_PUBLIC_DATA_BASE` | **Hobby** (non-commercial terms; quotas unmeasured: a register gap) | git integration with GitHub | login is the GitHub identity; if GitHub is recovered Vercel follows. Project settings are re-creatable from `site-branch-protocol.md` |
| **Domain registrar** for `ohmega.monster` | the domain and its DNS (nameservers possibly moved to Cloudflare) | domain fee | web login | registrar, renewal date and who holds the login: **unrecorded**. This is the one asset the repo cannot rebuild; record it first |
| **Supabase** (**paused 2026-10-22**) | an empty/paused Postgres project and Storage bucket `published-assets`; nothing reads it | free (paused) | none in use (`SUPABASE_*` are legacy) | delete the project once sure (the register says after 90 days, i.e. around 2027-01-20); the 42 charts that lived in its bucket are gone, see `foundation.md` |

## Model, search and data providers (losing one degrades a feature; keys are revocable and re-issued)

| Account | Holds / pays for | Key name(s) (`../credentials.md`) | Notes |
|---|---|---|---|
| **Meta model API (house model)** | research, writing, extraction: the main spend | `META_MODEL_API_KEY`, `META_MODEL_API_BASE_URL` | the watchdog caps spend ($15/run, $40/day) |
| **OpenAI**, **Anthropic**, **Google Gemini**, **xAI** | alternate model routes; Gemini also draws hero images | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, `XAI_API_KEY` | optional unless a route is selected |
| **Tavily**, **Exa**, **Brave**, **Firecrawl** | paid search / page-read, last resort, monthly caps in `tools/sourcing/search/quota.py` | `TAVILY_API_KEY`, `EXA_API_KEY`, `BRAVE_API_KEY`, `FIRECRAWL_API_KEY` | absent just skips that rung |
| **X (Twitter)** | two roles: the original funded account for **read/search**, and the Ohmega account for **posting** | `X_BEARER_TOKEN` (+ aliases); `X_API_KEY`, `X_API_KEY_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`, `X_POST_HANDLE` | posting is behind a human-approval gate (see memory note on X architecture) |
| **Free-keyed data feeds** | aisstream.io (sign in with GitHub), NASA FIRMS, GIE AGSI+, OpenSky | `ALGENT_AISSTREAM_KEY`, `ALGENT_FIRMS_KEY`, `ALGENT_AGSI_KEY`, `ALGENT_OPENSKY_CLIENT_ID`/`_SECRET` | free; the feed goes quiet without its key and `newsroom doctor` says so |
| **Chart harness logins** (grok-build, codex) | subscription-funded drawing of static charts; **per-machine logins, not keys** | none | must be logged in on whichever machine runs analytics |

Where the secrets themselves live: `~/algent.env` on the droplet (chmod 600, linked as `backend/.env`) and `backend/.env` plus the OS keyring on the
laptop. A password manager entry for each account above is **unrecorded**; if there is none, create it before anything else on this page.

## Quarterly recovery pass (15 minutes, put it in the calendar)

1. For each infrastructure account: can you sign in from a clean browser using only the password manager and the stored recovery codes? Tick it in the
   cell above (write the date, not the codes).
2. Fill every **unrecorded** cell with a *location* ("the password manager, entry X"; "paper in the safe"), not a secret.
3. `newsroom backup restore-drill` has an `ok` entry in `~/ops-log.md` from this month (the monthly timer runs it; `newsroom envelope` shows the age).
4. Revoke what is unused: stale deploy keys, API tokens for providers no longer routed, the Supabase project once it is safe to delete.
5. Check the Cloudflare budget alert and the card on file still exist (R2 and Vercel are the two places a lapsed card or an overage hurts).
