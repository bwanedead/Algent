# Repository Guidelines

## Project Structure & Module Organization
- `backend/` – Python agent ecosystem; core package lives in `backend/algent_backend/` with `agent_system/` (foundation/integration/orchestration), `labs/` (Algo Lab, News Hub stubs), `commands/`, `api/`, and `config/`.
- `frontend/` – React + Vite UI with a Tauri wrapper (`frontend/src-tauri/`); source components live in `frontend/src/`.
- `docs/`, `backend/docs/`, `frontend/docs/` – design notes, vision documents, and surface-specific write-ups.
- Tests reside under `backend/tests/` (mirror modules as they grow).

## Build, Test, and Development Commands
- Backend setup: `cd backend && python -m venv .venv && .venv\Scripts\Activate.ps1`.
- Backend run placeholder: `.venv\Scripts\Activate.ps1; python -m algent_backend.app` exposes `/health` on `http://127.0.0.1:43145`.
- Frontend install: `cd frontend && npm install`; dev server `npm run dev`; Tauri shell `npm run tauri:dev`.
- Tests (backend): `cd backend && .venv\Scripts\Activate.ps1 && pytest`.
- **Do not run `git` commands in this repo unless explicitly instructed by the maintainer.**
- **Do not install dependencies (pip, npm, cargo, etc.); the maintainer handles all installation. Stick to read-only commands unless told otherwise.**

## Coding Style & Naming Conventions
- Python: PEP8-ish, 4-space indent, type hints when possible. Place shared types in `agent_system/foundation/...` as needed.
- TypeScript: Follow default Vite/React conventions; components in `PascalCase`, hooks/utilities in `camelCase`.
- Keep modules small and labeled (e.g., `labs/<lab>/experiments.py`). Prefer descriptive docstrings and TODO markers for future work.

## Testing Guidelines
- Use `pytest`; mirror backend modules under `backend/tests/` (e.g., `test_agent_system.py`, `test_labs.py`).
- Name tests `test_<behavior>` and keep assertions focused on public APIs/registries.
- When adding new command/loop/lab logic, add at least a sanity test covering the main happy path.

## Commit & Pull Request Guidelines
- Commit messages follow short imperative style (`“add agent system skeleton”`); keep commits scoped and reference the area touched.
- PRs should describe scope, mention testing performed (`pytest`, `npm run dev` smoke), and link issues/tasks when applicable.
- Include screenshots or logs only when UI or observability changes are made.

## Architecture Overview
- Agents are assembled via `agent_system/` (loops + model providers + tool registry) and dispatched through labs, aligning with the holistic vision in `docs/holistic-vision.md`.
- Commands flow from the frontend terminal (`frontend/src/components/TerminalPanel.tsx`) to backend handlers in `commands/` and on toward lab services.
- Credentials are updated through `/credentials` (called by `components/ApiKeyManager`), which stores provider keys via keyring or env vars.

## Architecture & Design Ethos
Our top priority is **high structural soundness and sanity**: clean, modular, scalable architecture built with solid best practices. Whenever there is a tradeoff, **always prefer structurally sane, high-quality design over quick fixes or shortcuts**.

- **Architecture first.** Before adding code, ask: *How does this fit into the overall structure?* Create or extend well-defined modules instead of stuffing more logic into whatever file is closest.
- **Modular and scalable by default.** Keep responsibilities narrow and interfaces clear. Design modules so they can grow and be reused without hacks.
- **No spaghetti, ever.** Tangled dependencies, unclear ownership, circular imports, and cross-cutting side effects are red flags. If an approach leads toward spaghetti, it must be redesigned, not shipped.
- **Best practices over convenience.** When choosing between a quick patch and a small refactor that preserves or improves the architecture, always choose the refactor.

The agent should consistently favor decisions that increase or preserve structural sanity, even when that requires more effort in the short term.
