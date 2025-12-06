# Backend (Python)

This directory hosts the minimal Python skeleton for Algent.

## Virtual environment

- Recommended location: `.venv` inside `backend/`.
- Create: `python -m venv .venv`
- Activate (PowerShell): `.venv\\Scripts\\Activate.ps1`
- Install deps (once defined): `pip install -r requirements.txt`

## Entrypoint

- `algent_backend/app.py` exposes a temporary HTTP health endpoint using only the standard library. Replace with FastAPI/Flask/etc. once chosen.
- Run locally: `python -m algent_backend.app`

## Module layout (initial placeholders)

- `algent_backend/algorithms/` – algorithm implementations and helpers.
- `algent_backend/metrics/` – metric calculators and reducers.
- `algent_backend/experiments/` – experiment definitions, run orchestration, and result capture.
- `algent_backend/commands/` – command schema and dispatch layer for both human and agent-issued actions.
- `algent_backend/config/` – runtime/config defaults, environment helpers.
- `algent_backend/api/` – HTTP/API surface (currently just health).

Each module includes TODO notes for future expansion; nothing here is locked-in yet.
