# Credentials & API Keys

Algent prefers reading provider API keys from environment variables, but can fall back to the system keyring for convenience.

## Order of Precedence
1. Environment variables (set before starting the backend / Tauri app)
2. Keys saved via the in-app **Model API Keys** panel (writes to keyring)
3. Keyring entries added manually under service `algent` (per provider username)

If neither is present, provider calls will fail until keys are supplied.

## Supported Providers

| Provider  | Env Var               | Keyring Username      | Default Model         |
|-----------|----------------------|-----------------------|-----------------------|
| OpenAI    | `OPENAI_API_KEY`     | `openai_api_key`      | `gpt-5.6-luna` (via `openai_spec`) |
| Meta      | `META_MODEL_API_KEY` | `meta_model_api_key`  | `muse-spark-1.2-contributor` (house default) |
| Anthropic | `ANTHROPIC_API_KEY`  | `anthropic_api_key`   | `claude-3-5-sonnet`   |
| Gemini    | `GEMINI_API_KEY` \*  | `gemini_api_key`      | `gemini-1.5-pro`      |
| xAI       | `XAI_API_KEY`        | `xai_api_key`         | `grok-beta`           |

\* Gemini will also fall back to `GOOGLE_API_KEY` if `GEMINI_API_KEY` is absent.

## Managing Keys with Keyring

Store + verify keys using Python’s keyring CLI (after installing `keyring` in your environment):

```powershell
python -m keyring set algent openai_api_key
python -m keyring get algent openai_api_key
```

Repeat for other providers using the usernames from the table above.

## Tips
- Never hardcode secrets into source files or commit history.
- When testing multiple providers, prefer setting per-shell env vars (`$env:OPENAI_API_KEY="..."`) so you can swap quickly.
- For deployments beyond personal use, consider vault-backed solutions; this keyring workflow is intended for local developer ergonomics.
- The frontend button is the fastest way to rotate a key: select provider → paste key → Save. Running the backend during this step is enough; no restarts required unless the provider client caches credentials.

## Key manifest (names only — what each is for, who reads it)

Values live only in `backend/.env` on each machine (and the keyring on the laptop); never in git. On the
worker server the file is `~/algent.env` (chmod 600), linked as `backend/.env` by `infra/server/app_setup.sh`.

| Key | Purpose | Read by | Needed for |
|---|---|---|---|
| `META_MODEL_API_KEY`, `META_MODEL_API_BASE_URL` | house model (research, writing, extraction) | `config`, `foundation/models/targets/langchain.py` | everything that calls a model |
| `OPENAI_API_KEY` | OpenAI models | `config/providers` | OpenAI-routed calls |
| `ANTHROPIC_API_KEY` | Anthropic models | `config/providers/anthropic.py` | Anthropic-routed calls |
| `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | Gemini models; hero images | `config/providers/google.py`, `editorial/image_gen.py` | images, Gemini calls |
| `XAI_API_KEY` | xAI/Grok API models | `config/providers/xai.py` | Grok-routed calls |
| `TAVILY_API_KEY`, `EXA_API_KEY`, `BRAVE_API_KEY` | PAID search, last resort (monthly caps in `tools/sourcing/search/quota.py`) | `get_service_api_key` | only when every free engine failed |
| `FIRECRAWL_API_KEY` | PAID page read, last resort (capped) | `depth/fetch_content.py` | rare walled pages |
| `X_BEARER_TOKEN` (aliases: `X_API_BEARER_TOKEN`, `X_BEARER`, `X_BEARER_KEY`, `TWITTER_BEARER_TOKEN`) | X **read/search** — the original funded account | `data_ingestion/.../x_native.py`, `config/providers/x.py` | X discovery, X search |
| `X_API_KEY`, `X_API_KEY_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`, `X_POST_HANDLE` | X **posting** as the Ohmega account | `publishing/x_client.py` | radar/briefing/article posts |
| `LANGSMITH_*` | optional deep traces | LangChain | nothing (optional) |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_BASE` | **server-only** Cloudflare R2 (the published-file store): the backend signs S3-API requests (SigV4, region `auto`, path-style `https://<account>.r2.cloudflarestorage.com/<bucket>/<key>`) with an R2 API token scoped to the one bucket (Object Read & Write). `R2_BUCKET` is `ohmega`; `R2_PUBLIC_BASE` is the bucket's public URL (`https://pub-….r2.dev`, later `https://data.ohmega.monster`) and must equal the site's `NEXT_PUBLIC_DATA_BASE`. **The access key pair is a write credential: worker env only, never in Vercel, never committed.** The account has a card on file: the free-tier guard (`publishing/object_budget.py`) hard-stops writes at 90% of the monthly free tier | `publishing/object_store.py`, `asset_store.py` | publishing is a no-op (a `SITE_PUBLISH_VIA = "db"` publish errors with a clear note) |
| `R2_BACKUP_BUCKET` | **server-only:** the name of a **private** R2 bucket (no public access, no r2.dev) for the nightly snapshots (`backups/daily/<date>.tar.gz`). Same `R2_ACCOUNT_ID` / key pair as above, so the R2 API token must cover this bucket too (Object Read & Write on both buckets, or an account-scoped token). There is deliberately no fallback to the public bucket | `publishing/object_store.select_backup`, `data_backup/snapshot.py` | `newsroom backup snapshot` reports "no backup bucket"; `newsroom envelope` fails the backup row |
| `NEXT_PUBLIC_DATA_BASE` | the **site's** only data setting (set in Vercel, Production + Preview; inlined at build time, so redeploy after changing it): the public URL prefix of the bucket. Public by design | `sites/ohmega-monster/lib/data-base.ts` | unset: the site reads its content files and `/public` images |
| `DATABASE_URL` | **optional, legacy:** Supabase Postgres (session-pooler URI). Used only when `database/flags.POSTGRES_PUBLISH` or `PULSE_BACKEND = "postgres"` is switched on, and by `newsroom db export-pulses` | `database/migrate.py`, `pulse/repository.py` | nothing (the file stores are the record) |
| `ALGENT_OBJECT_BACKEND`, `ALGENT_POSTGRES_PUBLISH`, `ALGENT_PULSE_BACKEND` | not credentials: one-shot process overrides of the three flags in `database/flags.py` (`r2`/`supabase`, `1`, `files`/`postgres`) | `database/flags.py` | the checked-in flag |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | **optional, legacy, server-only:** Supabase Storage writes when `database/flags.OBJECT_BACKEND = "supabase"`. A master key: backend/worker env only, never in Vercel. The site no longer reads `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` (remove them from Vercel) | `publishing/object_store.py` | unused with the R2 backend |
| `ALGENT_JINA_KEY` | optional: higher Jina limits | `depth/free_rungs.py` | optional |
| `ALGENT_AGSI_KEY` | GIE AGSI+ API key (free registration at agsi.gie.eu): without it the `gas_eu_storage` series stays empty and reports "needs AGSI key (free registration)"; `newsroom instruments show` and `newsroom doctor` list it as overdue until set | `instruments/sources/agsi.py` | optional (operator registers) |
| `ALGENT_FIRMS_KEY` | NASA FIRMS MAP_KEY (free registration at https://firms.modaps.eosdis.nasa.gov/api/map_key/): without it the `firms` live feed reports "needs ALGENT_FIRMS_KEY (free registration at ...)" and the fire-hotspot layer stays empty | `live/feeds/firms.py` | optional (operator registers) |
| `ALGENT_AISSTREAM_KEY` | aisstream.io API key (free, sign in with GitHub at https://aisstream.io/authenticate): without it the AIS service exits reporting "needs ALGENT_AISSTREAM_KEY" and our own chokepoint ship counts (`live_ais_*`) are not collected | `live/feeds/ais.py` | optional (operator registers) |
| `ALGENT_OPENSKY_CLIENT_ID`, `ALGENT_OPENSKY_CLIENT_SECRET` | OpenSky Network OAuth2 API client (free account: register at https://opensky-network.org/, then Account page -> create an API client). Optional: without them the sky board still gets the world from OpenSky anonymously (400 credits a day = one global call per 15 min); with them 4 000 credits a day = one call per 2 min. Fair use: research / non-commercial, cite OpenSky (the /live credit line does) | `live/ingest/opensky.py` | optional (operator registers) |
| `ALGENT_RELIEFWEB_APPNAME` | ReliefWeb API v2 `appname`. ReliefWeb refuses unapproved names (HTTP 403): request one at https://apidoc.reliefweb.int/parameters#appname. Until set the `reliefweb` source of the attack log reports `needs-key` | `conflict/sources/reliefweb.py` | optional (operator registers) |
| `ALGENT_ACLED_EMAIL`, `ALGENT_ACLED_PASSWORD` | ACLED account (free for research use; register at https://acleddata.com/register/): the best curated attack source. Until set the `acled` source reports `needs-key` | `conflict/sources/acled.py` | optional (operator registers) |
| `ALGENT_UCDP_TOKEN` | UCDP API access token (request as described at https://ucdp.uu.se/apidocs/): GED candidate events with fatalities. Until set the `ucdp` source reports `needs-key` | `conflict/sources/ucdp.py` | optional (operator registers) |

**Not keys but per-machine logins** (subscription-funded, no API key): the chart harnesses `grok-build` (default)
and `codex` (fallback) — each must be logged in on whichever machine runs analytics.

**To do:** give the server its own provider keys (distinct from the laptop's) so either can be revoked alone.
