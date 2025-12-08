# Algent

Algorithm behavior lab – desktop app for experimenting with algorithms and their emergent behaviors.

## Structure

- `backend/` – Python skeleton with a stdlib HTTP health endpoint and placeholders for algorithms, metrics, experiments, commands, and config. Binds to `127.0.0.1:43145` by default to avoid port clashes.
- `frontend/` – React + Vite shell with a Tauri wrapper. Includes layout, terminal-like command panel, metrics and visualization placeholders, and a tiny backend client.
- `docs/` – project-wide documentation hub (vision, roadmap, general notes), plus per-surface docs under `backend/docs/` and `frontend/docs/`.
- `docs/credentials.md` – instructions for providing API keys via environment variables or keyring.

## Quickstart (dev shells)

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1  # or source .venv/bin/activate on Unix
# pip install -r requirements.txt  # once deps are chosen
python -m algent_backend.app  # serves http://127.0.0.1:43145/health
```

### Frontend (web)
```bash
cd frontend
npm install
npm run dev
```

### Frontend (Tauri desktop)
```bash
# rust + tauri pre-reqs must be installed
cd frontend
npm install
npm run tauri:dev
```

### API Keys
- Preferred: open the web/Tauri shell and use the **Model API Keys** panel to pick a provider, paste your key, and save (writes to keyring when available).
- Alternatively, set provider API keys via environment variables (e.g., `OPENAI_API_KEY`) or store them manually with `python -m keyring set algent openai_api_key`. See `docs/credentials.md` for the full matrix.
