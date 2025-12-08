# Backend (Python)

This directory hosts the minimal Python skeleton for Algent.

## Virtual environment

- Recommended location: `.venv` inside `backend/`.
- Create: `python -m venv .venv`
- Activate (PowerShell): `.venv\\Scripts\\Activate.ps1`
- Install deps (once defined): `pip install -r requirements.txt`

## Entrypoint

- `algent_backend/app.py` exposes a temporary HTTP health endpoint using only the standard library. Replace with FastAPI/Flask/etc. once chosen.
- Run locally: `python -m algent_backend.app` (binds to `127.0.0.1:43145` by default to avoid conflicts and stay machine-local).

## Module layout (initial placeholders)

- `algent_backend/agent_system/` – core agent infrastructure split into `foundation/` (loops, models, prompting), `integration/` (tools/adapters), and `orchestration/` (multi-agent runners).
- `algent_backend/labs/` – pluggable domains (“work vectors”) such as `algo_lab/` (current focus) and `news_hub/` (stub).
- `algent_backend/commands/` – command schema and dispatch layer for both human and agent-issued actions.
- `algent_backend/api/` – HTTP/API surface (currently just health).
- `algent_backend/config/` – runtime/config defaults and settings loaders.
- `algent_backend/docs/` – backend-specific design notes.
- `tests/` – mirrors agent system/lab modules as coverage grows.

Each module includes TODO notes for future expansion; nothing here is locked-in yet.

## Credentials

- API keys are read from environment variables first (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.).
- If unset, the backend looks for a keyring entry under service `algent` (username `<provider>_api_key`, e.g., `openai_api_key`). Add them via `python -m keyring set algent openai_api_key`.
- The `/credentials` HTTP endpoint accepts `POST {"provider": "...", "api_key": "..."}` to store keys (used by the frontend panel).
- See `../docs/credentials.md` for the full mapping.
