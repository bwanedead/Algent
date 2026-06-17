# Documentation Hub

Project-wide documentation lives here. Surface-specific docs live in `backend/docs/` and
`frontend/docs/`; component-internal notes (e.g. `backend/algent_backend/graph_os/docs/`)
stay next to their code.

## How we keep docs organized

Docs sprawl is a real failure mode. To prevent it:

- **Every doc belongs to a category folder** (below). Don't drop loose files at the docs
  root — the root holds only this index.
- **One canonical home per topic.** If a topic already has a doc, extend it rather than
  starting a parallel one. Merge or retire stale docs instead of stacking new ones
  (see `ethos/raptor-3-ethos.md`).
- **Vision ≠ architecture ≠ ethos ≠ guides.** Keep aspirational narrative, current
  structure, governing principles, and how-to instructions in their own lanes.
- **Add the doc to this index** in the same change that creates it.

## Categories

| Folder | Contents |
|--------|----------|
| `ethos/` | Governing principles and design philosophy. |
| `architecture/` | How the system is actually built today (structure, stack). |
| `vision/` | Aspirational direction, roadmap, phase narratives. |
| `linting/` | Static-analysis and governance policy. |
| `guides/` | Operational how-tos (setup, credentials, onboarding). |
| `responses/` | Point-in-time analyses and summaries. |

## Index

### Ethos — `ethos/`
- `architecture-ethos.md` – layer separation, no God objects.
- `structural-ethos.md` – weight-bearing layers, robustness over cleverness.
- `modularity-ethos.md` – decomposition: one home per responsibility, no junk drawers.
- `raptor-3-ethos.md` – native-integration / subtractive design.
- `doctrine-drafting-ethos.md` – how to author agent prompt doctrine.
- `harness-ethos.md` – mechanics vs. semantic authorship; the agent-native rule.
- `agent-ergonomics-ethos.md` – fit the action seam to the agent's natural grammar; discover it empirically.

### Architecture — `architecture/`
- `run-control-plane.md` – run directory contract, runs CLI, observability weave.

### Guides — `guides/`
- `run-operator-entrypoint.md` – **start here** to operate runs; hub that routes to the rest.
- `agent-cli-testing.md` – CLI mechanics: discover/start/watch/stop an agent run.

### Linting — `linting/`
- `static-governance.md` – lint toolchain, rules, and what blocks vs. warns.

### Architecture, Vision, Guides
> These existing docs currently live at the docs root. They stay where they are; the
> category folders apply to **new** docs going forward.

- Architecture: `algent-backend-architecture.md`, `tech-stack.md`
- Vision: `holistic-vision.md`, `project-vision.md`, `algo-lab-vision.md`,
  `agent-network-vision.md`, `workspace-agentic-vision.md`, `aesthetic-vision.md`,
  `PHASE_2_VISION.md`
- Guides: `credentials.md`
- Responses: `responses/phase-2-inoculation-summary.md`
