# PRD: Ralph Cockpit

## Context
Ralph Engine runs are currently driven by CLI commands and manual inspection of files in `ralph/runs/<run_id>/`. This is slow, error-prone, and difficult to operate across multiple repos. We need a dedicated cockpit inside Algent that can observe and control runs using the file-based contracts Ralph Engine already uses.

## Goal
Deliver a local, calm operator cockpit in the Algent UI that lists Ralph runs, inspects their state/artifacts, and writes control signals to guide execution.

## Non-goals
- No new Ralph Engine features or protocol changes.
- No cloud/remote operation; this is a local-only cockpit.
- No major refactors of the existing Algent UI layout or architecture.
- No new authentication or user management.

## Users / Use cases
- As an operator, I want to see all runs in a repo and their status so I can quickly decide which to intervene on.
- As a developer, I want to inspect run artifacts (PRD/progress/stories/events) without leaving the UI.
- As a run owner, I want to pause, stop (soft/hard), or trigger review actions via UI controls that write to `control.json`.
- As a runner, I want to generate or trigger `ralph-engine` commands from the cockpit.

## Scope
- Frontend cockpit UI in Algent with a new `/cockpit` page.
- A local bridge (Tauri or backend) for file reads, file writes, and process spawning.
- Reading/parsing: `run.json`, `control.json`, `events.ndjson`, `PRD.md`, `prd.json`, `progress.md`, and phase artifacts.
- Writing: `control.json` updates (toggles + one-shot actions).
- Command orchestration: command generator and/or CLI invocation for `ralph-engine`.

## Constraints / invariants
- Must preserve the existing Algent home page layout; only add a small cockpit entry point.
- Must be local-only (desktop bridge or backend proxy); no direct browser FS access.
- Must respect Ralph Engine file contracts and not mutate engine-owned files except `control.json`.
- Must handle missing files gracefully with clear diagnostics.
- Must match Algent’s current visual style (HUD aesthetic).

## Success criteria
- A cockpit entry point is visible on the home screen and opens a dedicated cockpit view.
- The cockpit can list runs under `ralph/runs/` and display basic metadata.
- Selecting a run shows `run.json` state, `control.json` state, PRD/progress text, and story status from `prd.json`.
- The cockpit can append or update control signals in `control.json` (pause, stop_soft, stop_hard, skip_iteration, review_now, review_next).
- The cockpit can generate and present `ralph-engine` commands for run/doctor/tail with driver selection.
- Missing/invalid files surface clear, actionable error states.

## Edge cases
- Repo has no `ralph/` directory.
- Run exists but `run.json` or `control.json` is missing.
- `events.ndjson` missing or empty.
- Template-run vs engine-native run styles.
- Paths with spaces (Windows).
- Engine process already running or cannot be spawned.
- Large event logs (needs tailing/pagination).

## Implementation notes (optional)
- Favor a local bridge approach (Tauri commands or backend endpoints) for:
  - listing repos and runs
  - reading files
  - writing `control.json`
  - tailing `events.ndjson`
  - spawning `ralph-engine` processes
- Ralph Engine is available at `C:\projects\ralph-engine`; CLI invocation should reference that path or a stable executable name.
- Keep cockpit UI modular: sidebar (repo/runs), main detail panes, events tail, and control panel.
