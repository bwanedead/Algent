# Technical Stack Overview

High-level snapshot of the technologies powering Algent. Update this file as the
stack evolves.

## Backend

- **Language**: Python 3.11+
- **Runtime**: Standard library HTTP server (placeholder) – will be replaced by a chosen framework (FastAPI/Flask/etc.).
- **Structure**: `backend/algent_backend/` package with modules for algorithms, metrics, experiments, commands, config, API.
- **Virtual environment**: `backend/.venv` (per-project isolation).
- **Testing**: Pytest (stub tests already in `backend/tests/`).

## Frontend

- **Language**: TypeScript + React 18.
- **Bundler/Dev server**: Vite.
- **Desktop shell**: Tauri 1.x (Rust 2021 edition).
- **UI structure**: Main layout + terminal, metrics, visualization placeholders.
- **Command pipeline**: `frontend/src/client/backendClient.ts` for HTTP calls to backend.

## Tooling & Misc

- **Package managers**: `pip` (via venv) for backend, `npm` for frontend, `cargo` for Tauri.
- **Docs**: Markdown under `docs/`, with surface-specific folders (`backend/docs/`, `frontend/docs/`).
- **Version control**: Git (LF-normalized; .venv/node_modules ignored).
