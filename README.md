# Algent

Algorithm behavior lab – desktop app for experimenting with algorithms and their emergent behaviors.

## Structure

- `backend/` – Python skeleton with a stdlib HTTP health endpoint and placeholders for algorithms, metrics, experiments, commands, and config.
- `frontend/` – React + Vite shell with a Tauri wrapper. Includes layout, terminal-like command panel, metrics and visualization placeholders, and a tiny backend client.

## Quickstart (dev shells)

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1  # or source .venv/bin/activate on Unix
# pip install -r requirements.txt  # once deps are chosen
python -m algent_backend.app
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
