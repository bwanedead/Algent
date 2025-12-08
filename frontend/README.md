# Frontend (React + Tauri)

Minimal shell for the Algent desktop UI. Uses Vite for the web layer and Tauri
for the desktop wrapper.

## Install (later)

```bash
cd frontend
npm install
# or: pnpm install / yarn
```

## Run (web)

```bash
npm run dev
```

## Run (Tauri desktop)

```bash
# ensure Rust + Tauri prerequisites are installed
npm run tauri:dev
```

## Structure

- `src/` contains React components:
  - `components/MainLayout` wires the overall shell.
  - `components/ApiKeyManager` surfaces the quick API-key setter (talks to `/credentials`).
  - `components/TerminalPanel` is the command entry/log view.
  - `components/MetricsView` and `WorldView` are placeholders for visual layers.
- `src/client/backendClient.ts` provides a tiny HTTP client to the Python backend (defaults to `http://127.0.0.1:43145` for local dev).
- `src-tauri/` hosts the desktop wrapper config and Rust entrypoint.
