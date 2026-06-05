# Static Governance & Linting

This document explains Algent's static-analysis setup: what tools run, what each one
enforces, what blocks versus warns, and the reasoning behind those choices. It is the
canonical home for lint policy — change a rule here in the same patch that changes the
config.

The guiding philosophy follows `docs/ethos/` (especially `modularity-ethos.md` and
`raptor-3-ethos.md`):

> **Lint applies soft pressure, not hard bumpers.** The only hard failures are genuine
> bugs (undefined names, unused imports, syntax). Size, package shape, and even
> architectural import boundaries surface as **warnings** — pressure that's enough to
> prompt the right fix without blocking normal work.

We set this up **before** the code grows. Algent has no legacy monolith debt, so unlike
damage-control setups we need no growth budgets or per-file baselines — we set sensible
standards now and let them shape the code as it lands. The boundary rules currently have
nothing to fire on (the packages they watch don't exist yet); they activate automatically
as those packages appear.

---

## Toolchain

| Tool | Role | Severity |
|------|------|----------|
| **ruff** | style, imports, unused code, complexity, likely-bug patterns | real bugs block; style is auto-fixed |
| **mypy** | type checking | **non-blocking** (promote once typed coverage is real) |
| **governance script** (`tools/governance.py`) | size pressure, flat-package shape, import-boundary drift | **soft (warns, exits 0)** |
| **pre-commit** | local gate; auto-fixes hygiene before commit | local |
| **GitHub Actions** | CI gate | only ruff bugs block |

Everything is off-the-shelf except one small stdlib-only script. We deliberately do **not**
use a dedicated import-contract tool (e.g. import-linter): those are pass/fail by design,
and with all boundaries soft, an AST check inside the governance script is the leaner fit.
If we ever want hard, transitive-aware boundary enforcement, import-linter is the upgrade
path.

Config locations:
- `backend/pyproject.toml` — ruff + mypy.
- `tools/governance.py` — size / shape / boundary warnings (run: `python tools/governance.py`).
- `.pre-commit-config.yaml` — local hooks.
- `.github/workflows/static-governance.yml` — CI.

---

## What blocks vs. what warns

| Check | Severity | Enforced by |
|-------|----------|-------------|
| Real bugs: undefined names, unused imports, syntax (ruff `F`/`E9`) | **Error** | ruff |
| Style / formatting / complexity | auto-fixed; **non-noisy** | ruff |
| Import-boundary drift (rail isolation, definitions purity, layering, decoupling, adapter seam) | **Warn** | governance script |
| File approaching size pressure (≈800 lines) | **Warn** | governance script |
| File over soft ceiling (≈1000 lines) | **Strong warn** | governance script |
| Loose modules at a domain package root | **Warn** | governance script |
| Type errors | **Non-blocking** | mypy |

The governance script always exits 0. (It accepts `--strict` to exit non-zero on any
finding, for ad-hoc audits — but the default and the CI invocation are soft.)

---

## Rules

### 1. File size — soft pressure, no hard cap
- **~800 code lines:** a notice ("getting large — check for a second responsibility").
- **~1000 code lines:** a strong warning ("split or reduce before growing further").
- **No hard block.** Files up to ~1000 lines are tolerated; the warning escalates rather
  than forbids. Counts ignore blank lines and pure comments. A high backstop above 1000 is
  deferred unless warnings start getting ignored at scale.

### 2. Package shape — discourage flat dumping (soft)
The top level of a watched domain package (currently `agent_system/`) should be
`__init__.py` plus subpackages, not loose implementation files. The script **warns** on
loose top-level modules. Flat sometimes has to happen, so it nudges rather than forbids —
encoding `modularity-ethos.md` §3 as gentle pressure.

### 3. Architectural import boundaries — warnings
Enforced by the governance script via AST import analysis (direct imports; absolute and
relative). Each is objective, but a warning is enough to surface the right fix.

1. **Rail isolation.** `langchain` / `langgraph` / `langsmith` may be imported only within
   `agent_system/runtime/**`, `agent_system/agents/**`, and
   `agent_system/foundation/models/targets/**`.
   *The highest-value rule: it keeps the rail framework out of the neutral core (`runs/`,
   `runtime/base.py`, etc.).*
2. **`definitions/` purity.** A `definitions` module must not import other `agent_system`
   internals — contracts depend on nothing.
3. **graph_os decoupling.** `agent_system/**` must not import `graph_os/**` and vice-versa,
   until a deliberate run-ledger projection seam exists.
4. **Transport layering.** `agent_system/`, `graph_os/`, and `labs/` must not import
   `algent_backend.api.*` — logic never depends upward on transport.
5. **Adapter seam.** Rail adapters under `runtime/**` (e.g. `runtime/langgraph.py`) are
   reached only via `runtime/registry.py`, not imported directly by callers.

### 4. Test placement — convention, not enforcement
Industry-standard layout per `AGENTS.md`: tests under `backend/tests/`, mirroring the
module, named `test_<behavior>`. No lint rule — convention plus review is enough.

### 5. Style, imports, complexity — ruff
Formatting, import order, unused imports/vars, modernizations, likely-bug patterns, and
mccabe complexity (max 10). Real bugs block; everything else is auto-fixable
(`ruff check --fix`, `ruff format`) and applied by pre-commit, so it rarely blocks. `E501`
is left to the formatter rather than reported as a lint error.

### 6. Types — mypy (non-blocking)
Runs but does not block, mirroring the standard "defer typecheck until coverage is real"
pattern. Promote to blocking once the typed surface is large enough to stay green.

---

## Working with findings

1. Decide whether the finding is real drift or a false signal.
2. **Prefer fixing the code.** A boundary warning usually means a seam was crossed —
   route through the registry, move the import to an adapter, keep a contract pure, etc.
3. Only relax a rule or threshold when the exception is **deliberate and structurally
   justified** — and document the change here in the same patch.

To extend policy: prefer cheap, deterministic, high-signal rules; start narrow; keep
health/size/boundary rules soft. Add a rule when a real regression motivates it, not
speculatively.

---

## Deliberately deferred
- Growth budgets / per-file baselines (no legacy debt to grandfather).
- A dedicated import-contract tool (import-linter) for transitive / hard enforcement.
- Frontend governance (add when the frontend grows real layer boundaries).
- Touched-file size escalation; a hard file-size backstop above the soft ceiling.
- Promoting mypy to blocking.

---

## Setup notes
- `ruff`, `mypy`, and `pre-commit` are already pinned in `backend/requirements.txt`;
  per `AGENTS.md` the maintainer installs them.
- Enable the local gate once: `pre-commit install` (from the repo root).
- `tools/governance.py` is stdlib-only and runs without any install.
