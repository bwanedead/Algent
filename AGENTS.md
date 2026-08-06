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
- **Do not install dependencies (pip, npm, cargo, etc.); the maintainer handles all installation. Stick to read-only commands unless told otherwise.**

## Git hygiene (standing duty — not optional)
Keep a **sane working tree** and a **remote backup** as work lands. Do not let large uncommitted piles accumulate.

- **Commit when a chunk is done.** After a coherent unit is correct (a feature slice, a fix, a doctrine pass, a testable batch — typically once reviewers/self-review are settled for non-trivial work), commit it. Prefer several small scoped commits over one mega-commit at end of day.
- **Push after committing.** Push the feature branch to `origin` so remote holds the backup. Do not wait for the human to ask unless push is blocked.
- **Branch only — never commit to `main`.** Work on `organic-dev` or a topic branch.
- **Before every commit:** `git status` + diff. Exclude secrets (`.env`, keys), run artifacts (`backend/runs_data/`), caches, build outputs, and one-shot local scratch. Update `.gitignore` when a new junk path appears.
- **Messages:** short imperative, scoped to the area (`feat(models): …`, `fix(editorial): …`).
- **Pause for confirmation only when consequential:** force-push, history rewrite, deleting others' work, or committing something ambiguous/secret-adjacent. Ordinary feature commits do **not** need a pre-ask.
- **Site-live content** still ships via the publish worktree / `site-live` branch — that path is separate from committing app code on `organic-dev`.

## Operator knobs (in-repo files — not `.env`)
Standing behavioral defaults (synthesis on/off, harness picks that are not secrets) live in **checked-in modules agents edit**, e.g. `backend/algent_backend/agent_system/agents/newsroom/flags.py`. Do **not** ask the human to set `.env` for those. `.env` / keyring stay for credentials and machine-local secrets only. Optional process env overrides are fine for one-shot runs.

## Safety & Blast-Radius (non-negotiable)
- **Stay inside the repo.** Never edit, create, or delete anything outside the repository root.
- **No destructive/wide commands.** Never run recursive or absolute-path deletions (`rm -rf /`, `rm -rf ~`, `Remove-Item -Recurse` against a drive/home, `del /s`, etc.). Never touch `.git/` internals.
- **No path traversal for writes/deletes.** No `..` traversal or absolute paths for edits or deletions.
- **Secrets are off-limits.** Never read, print, commit, or modify `.env`, keys, tokens, or credentials.
- **Disciplined deletions.** You may delete/move files *within* this repo for real refactors: remove usage first, keep the change minimal and justified, and explain what/why in the commit.
- **Do not touch `graph_os/`** unless the task explicitly targets it — it is the weight-bearing subsystem and stays decoupled from `agent_system/` until a deliberate seam exists.

## Read-First Behavior
- **Before any edit, read the repo-wide ethos** under `docs/ethos/` relevant to your scope — at minimum `architecture-ethos.md`, `structural-ethos.md`, and `modularity-ethos.md`; add `raptor-3-ethos.md` for refactors/convergence and `doctrine-drafting-ethos.md` for prompt/doctrine surfaces.
- **Honor local notes.** When editing inside a directory, first check for and read any `AGENTS.md`, `README.md`, or nearby `*-ethos.md` / `*-vision.md` in or above that directory (e.g. `backend/algent_backend/graph_os/docs/`).
- **Lint policy lives in one place.** Read `docs/linting/static-governance.md` before changing lint, CI, or governance rules. Treat the custom governance checks as architectural policy, not cosmetic style — but remember the philosophy is soft pressure, not hard bumpers (only real bugs block).
- **Docs stay organized.** New docs belong in a category folder per `docs/README.md`; extend the canonical doc for a topic rather than starting a parallel one.
- **Run logs are local — read them yourself.** A run's full record lives at `backend/runs_data/<run_id>/`. It is gitignored (hidden from git) but present on the filesystem and readable with your file tools — so to diagnose a run, read it directly rather than asking the maintainer to paste it: `audit/human/timeline.md` (human view), `audit/events.jsonl` (event trace), `audit/error.log` (full traceback on failure), and `child_stderr.log` / `child_stdout.log` (raw child output). Only the recent runs are kept (rolling retention); older history is in `runs_data/runs_index.jsonl`. (`.env` and other secrets remain off-limits — logs are not secrets.)

## Reviewer Subagents & Mandatory Review Flow
This repo defines reviewer subagents (under `.cursor/agents/` and `.claude/agents/`) to prevent two recurring failures: **monolith / boundary drift** and **code-mass inflation**. They are useful but token-expensive, so they run **on-demand behind per-harness toggles**.

A patch is **non-trivial** if it adds files, changes more than ~3 files, materially expands a file, introduces a new abstraction/helper/service, changes module or layer boundaries, or is a refactor/cleanup/reorganization.

**Per-harness toggles (edit this file):**

```
REVIEWER_SUBAGENTS_ENABLED__CLAUDE_CODE = false
REVIEWER_SUBAGENTS_ENABLED__CURSOR      = true
REVIEWER_SUBAGENTS_ENABLED__CODEX       = false
```

**Active harness:** use the toggle matching the tool running this session — **Claude Code** → `__CLAUDE_CODE`, **Cursor** → `__CURSOR`, **Codex** → `__CODEX`. New harnesses: add a `REVIEWER_SUBAGENTS_ENABLED__<KEY> = false` line and document it here.

**Policy:**
- If the **active harness** toggle is `true`, treat it as a license to self-infer *when* a review materially strengthens the repo (typically after batch/structural work) — token cost is a real constraint, so be thoughtful, not reflexive. For non-trivial patches run:
  - `architecture-reviewer` — structure, boundaries, layering, responsibility allocation.
  - `code-efficiency-reviewer` — implementation weight, complexity, duplication, abstraction cost.
- If the change concerns **refactors, migrations, or trunk-level convergence** (retiring scaffolding, rail-isolation, mechanical-vs-semantic boundaries, graph_os seams), also run `raptor-3-native-reviewer`.
- If the change concerns **doctrine or prompt surfaces** (agent method prompts, action-contract text, lab/domain law, tool-spec behavioral text, or live doctrine in `docs/ethos/`), also run `doctrine-ethos-reviewer`.
- If the toggle is `false`, perform a **self-review** against the same criteria and note `reviewers skipped by policy (<harness>: toggle off)` in your final summary.
- If the human explicitly asks for reviewers on a single change, treat it as a one-off exception regardless of toggle.

**Review output must** stay in scope, cite exact files/symbols, distinguish blocking vs advisory findings, and name the relevant ethos principle.

**Completion requirement:** a non-trivial patch is not done until either reviewers have run (toggle on) and findings are summarized/reconciled, or a self-review was performed and summarized (toggle off), including any blocking issues and their resolution.

## Folder-level `AGENTS.md` (compounding memory)
A folder-level `AGENTS.md` is a short, local sticky note: constraints, invariants, commands, gotchas. Create or update one **only** when you discover something that prevents repeated mistakes (a non-obvious invariant, a required workflow command, an auto-generated file not to hand-edit, a dependency-ordering constraint). Keep it factual, bullet-based, and under ~30–50 lines; use repo-relative paths. Do **not** spam these everywhere.

## Coding Style & Naming Conventions
- Python: PEP8-ish, 4-space indent, type hints when possible. Place shared types in `agent_system/foundation/...` as needed.
- TypeScript: Follow default Vite/React conventions; components in `PascalCase`, hooks/utilities in `camelCase`.
- Keep modules small and labeled (e.g., `labs/<lab>/experiments.py`). Prefer descriptive docstrings and TODO markers for future work.

## Testing Guidelines
- Use `pytest`; mirror backend modules under `backend/tests/` (e.g., `test_agent_system.py`, `test_labs.py`).
- Name tests `test_<behavior>` and keep assertions focused on public APIs/registries.
- When adding new command/loop/lab logic, add at least a sanity test covering the main happy path.

## Commit & Pull Request Guidelines
- Follow **Git hygiene** above: commit+push coherent chunks on the feature branch without waiting to be asked.
- Commit messages follow short imperative style (`feat(area): …`); keep commits scoped and reference the area touched.
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
