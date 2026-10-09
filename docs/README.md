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
- `information-ergonomics-ethos.md` – how reader-facing pages are built: overview→detail, one meaning per colour, shared scales, change made explicit, one popover grammar.
- `raptor-3-ethos.md` – native-integration / subtractive design.
- `doctrine-drafting-ethos.md` – how to author agent prompt doctrine.
- `harness-ethos.md` – mechanics vs. semantic authorship; the agent-native rule.
- `agent-ergonomics-ethos.md` – fit the action seam to the agent's natural grammar; discover it empirically.

### Architecture — `architecture/`
- `run-control-plane.md` – run directory contract, runs CLI, observability weave.
- `map-analytics-stack.md` – accurate country-scale map figures for the newsroom analytics path.
- `pulse-system.md` – Ohmega Pulse: situations, anchored Pulses, append-only influences, watches, storage.
- `instruments.md` – the numbers layer: free programmatic series (chokepoint transits, energy, rates, FX…), append-only store, moves vs each series' own history, evidence API.
- `statements.md` – the record of who said what: primary transcripts (Kremlin, White House, State, FCDO, No 10, EC, China MFA), quote-validated extraction, append-only ledger, recall API.
- `library.md` – Ohmega's own source library: curated trusted sources crawled politely into a local FTS5 index; ranked search that answers first in web_search.
- `actors.md` – power profiles of states: the one country registry, World Bank/OWID/Wikidata/IMF sources, append-only store, profile/compare, publish feed and actor pages.
- `intel-desk.md` – the intelligence desk: broad headline base, heat, per-theater novelty, new/active/quiet lifecycle, budgeted daily focus.

### Guides — `guides/`
- `run-operator-entrypoint.md` – **start here** to operate runs; short hub that routes to the rest.
- `worker-server.md` – the always-on server: what runs where (free jobs on timers, paid runs on request), how to trigger a run over SSH, access it holds, rebuild from nothing.
- `agent-cli-testing.md` – **canonical CLI guide**: full `runs` command/flag set, newsroom rail,
  post-t0 `--from-run`, promotion cooldown, watch/stop, cost rails, run layout.
- `ohmega-research.md` – Ohmega Research CLI: validate trial JSONL, build the offline report, synthetic demo, reproducible METR source audit (`audit-metr`); record schema and denominator policy.

### Vision — `vision/`
- `ohmega-research.md` – Ohmega Research: reproducible-studies charter; first program (non-interference goal frontier), intervention definition, hypothesis vs finding, trial protocol, 72-attempt pilot, roadmap, evidence inventory (METR source audit).

### Linting — `linting/`
- `static-governance.md` – lint toolchain, rules, and what blocks vs. warns.

### Architecture, Vision, Guides
> These existing docs currently live at the docs root. They stay where they are; the
> category folders apply to **new** docs going forward.

- Architecture: `algent-backend-architecture.md`, `tech-stack.md`
- Vision: `vision/ohmega-intelligence-engine.md` (**canonical for Ohmega's direction**), `holistic-vision.md`, `project-vision.md`, `algo-lab-vision.md`,
  `agent-network-vision.md`, `workspace-agentic-vision.md`, `aesthetic-vision.md`,
  `PHASE_2_VISION.md`
- Guides: `credentials.md`
- Responses: `responses/phase-2-inoculation-summary.md`
