# PRD: Ralph Cockpit (Algent)

## Context

Operating Ralph Engine runs is currently CLI and file-based. This makes it slow to inspect run state, monitor events, and apply control signals across multiple repos. A local UI cockpit is needed to select a repo, inspect runs, and manage control signals and engine execution without manual file edits.

## Goal

Deliver a local-only Cockpit UI inside Algent that can discover Ralph-enabled repos, list runs, inspect run artifacts, tail events, write control signals, and launch the Ralph Engine CLI.

## Non-goals

- Any cloud or remote-hosted UI or API.
- Refactoring existing Algent homepage or global layout.
- Replacing Ralph Engine or changing its file contracts.
- Implementing new Ralph Engine features.

## Users / Use cases

- As an operator, I want to select a local repo and see all Ralph runs so that I can monitor status quickly.
- As an operator, I want to inspect run artifacts (run.json, prd.json, PRD.md, progress, phases) so that I can understand progress and issues.
- As an operator, I want to toggle control signals (pause, stop, review now/next, skip) so I can manage execution safely.
- As an operator, I want to launch Ralph Engine with a selected driver and options so I can start or resume a run from the UI.

## Scope

- Frontend: add a small navigation entry to the homepage and a new `/cockpit` page with a blank-slate layout.
- Local bridge: Tauri commands or backend endpoints to access filesystem and spawn subprocesses.
- File integrations: read and parse `run.json`, `control.json`, `events.ndjson`, `prd.json`, `PRD.md`, `progress.md`, and phase artifacts.
- UI workflows: repo selection, run listing, run detail panels, control panel, and events tail.

## Constraints / invariants

- Must preserve the existing Algent homepage and global layout; only add a small Cockpit link/button.
- Local-only: access local filesystem and spawn local processes, not remote APIs.
- Must support both template runs (PROMPT.md + prd.json) and engine-native runs (task.md, review_result.json).
- Must not overwrite engine-owned files except via explicit control.json updates.
- Must handle Windows paths (e.g., `C:\projects\...`) and paths with spaces.
- Must degrade gracefully when files are missing or not yet created.

## Success criteria

- User can select a repo and detect Ralph-enabled repos (presence of `ralph/` folder).
- User can list runs under `ralph/runs/` with run_id, status, last updated, and completion percent.
- User can view run state, PRD, stories docket, progress, phase artifacts, and events stream.
- User can write control signals to `control.json` safely and see confirmation.
- User can launch Ralph Engine with a chosen driver and options and see process output.

## Architecture plan

- Introduce a local bridge layer (Tauri commands or backend endpoints) to:
  - list directories and detect repos with `ralph/`
  - read file contents and parse JSON/NDJSON
  - write `control.json` with safe merges
  - tail `events.ndjson` (polling or file watch)
  - spawn/stop `ralph-engine` subprocess and stream output
- Frontend should call this bridge; no direct filesystem or process access in the browser layer.
- Data parsing rules:
  - Template run: completion derived from `prd.json` story pass flags.
  - Engine-native: display `run.json` state and `review_result.json` when present.
  - Missing files: display an empty state and guidance without breaking the UI.

## UX plan

- Add a small "Cockpit" navigation button/link on the homepage.
- `/cockpit` page layout:
  - Left sidebar: repo selection + runs list.
  - Main area: tabs for State, PRD, Stories, Progress, Phases.
  - Right or bottom panel: Events tail and filters.
  - Control panel near the run header with safe toggle buttons.
- Keep styling aligned with existing Algent aesthetics and components.

## Edge cases

- Repo selected without `ralph/` folder (show empty state and guidance).
- Runs missing `run.json` or `events.ndjson` (show "not started" state).
- Template runs missing worker/reviewer artifacts (non-fatal).
- Permission errors reading or writing files.
- `events.ndjson` is large; tail should be incremental and not block UI.
- Engine process already running or fails to spawn.

## Testing plan

- Manual test script:
  - Select a repo with `ralph/`.
  - Verify runs list loads and shows completion percentage.
  - Open a run and view each panel (State, PRD, Stories, Progress, Phases).
  - Toggle pause/stop flags and verify `control.json` changes.
  - Tail events and verify new lines appear.
  - Launch engine and verify process output is visible.
- Automated tests (minimal):
  - Unit tests for parsing `prd.json` and completion percentage.
  - Unit tests for control.json write merge logic.

## Integration points

- CLI patterns:
  - `ralph-engine run <repo> --run-id <run_id> --driver <driver> --max-iterations N`
  - `ralph-engine doctor <repo>`
  - `ralph-engine list <repo>`
  - `ralph-engine tail <repo> --run-id <run_id>`
- Local bridge should map UI controls to these commands and file operations.

## Local environment assumptions

- OS: Windows 10+.
- Python 3.11.4 available (`py -V`).
- `ralph-engine` repo exists at `C:\projects\ralph-engine` and CLI is available.
- Algent repo runs locally in dev mode.
