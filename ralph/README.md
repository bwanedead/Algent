# Ralph System

Ralph is a structured workflow for autonomous coding agents. It breaks features into atomic stories, tracks progress in machine-readable state, and enables iterative implementation via a repeated prompt loop.

## What Ralph Does

1. **Define** a feature precisely in a PRD
2. **Break** it into tiny, atomic stories with objective acceptance criteria
3. **Convert** to `prd.json` (machine-readable story list)
4. **Run** a loop where an agent repeatedly receives the same prompt, using repo state as memory
5. **Track** progress via `progress.md` and per-story summaries

## Directory Structure

```
ralph/
├── README.md           # This file
├── templates/          # All templates for creating runs
└── runs/               # Per-run directories
    └── <run_id>/       # Individual run folder
        ├── PRD.md      # Human-readable spec (required)
        ├── prd.json    # Atomic stories (required)
        ├── PROMPT.md   # Loop prompt (required)
        ├── progress.md # Short-term memory (required)
        └── ...         # Optional files (SUMMARY.md, transcripts/, etc.)
```

## Quick Start

1. Read `templates/HOW_RALPH_WORKS.md` to understand the loop mechanics
2. Read `templates/STORY_GUIDELINES.md` to understand what makes a good story
3. Follow `templates/RUN_CHECKLIST.md` to create a new run
4. Use `templates/PREP_AGENT_CHECKLIST.md` for detailed prep instructions

## Templates Reference

| Template | Purpose |
|----------|---------|
| `HOW_RALPH_WORKS.md` | Core loop mechanics explanation |
| `STORY_GUIDELINES.md` | What makes a good atomic story |
| `PRD_TEMPLATE.md` | Human-readable PRD format |
| `PRD_JSON_TEMPLATE.json` | Machine-readable story list format |
| `PRD_JSON_SCHEMA.md` | Schema documentation for prd.json |
| `PROMPT_TEMPLATE.md` | The prompt that runs each iteration |
| `SUMMARY_TEMPLATE.md` | Per-story debrief format |
| `TRANSCRIPT_TEMPLATE.md` | Per-iteration log format |
| `REVIEW_TEMPLATE.md` | Review cadence output format |
| `STEERING_TEMPLATE.md` | Steering notes format |
| `VISION_TEMPLATE.md` | High-level intent format |
| `LOOP_STATE_TEMPLATE.json` | Control plane state format |
| `CONTROL_PLANE.md` | Permissions matrix by mode |
| `RUN_CHECKLIST.md` | Pre-run validation checklist |
| `RUN_SKELETON.md` | Required/optional files reference |
| `RUN_SKELETON_CONTRACT.md` | Minimal valid run requirements |
| `PREP_AGENT_CHECKLIST.md` | Full prep workflow |
| `COMPATIBILITY_NOTES.md` | Loop compatibility requirements |
| `INVOKE_RALPH.md` | How to start a Ralph loop |

## Run Naming Convention

Use a stable run-id format:
```
YYYY-MM-DD__short-slug
```

Example: `2026-01-23__user-auth-flow`

## Versioning

This repository is the canonical source for Ralph templates. Use `ralph-services` to sync templates to projects:

```
/ralph-services --init <project-path>    # Bootstrap Ralph into a project
/ralph-services --update <project-path>  # Sync templates from canonical source
/ralph-services --doctor <project-path>  # Validate Ralph setup
```
