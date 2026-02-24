# GraphOS System Deep Dive (Implemented Reality + Architectural Review)

## Purpose and Scope

This document explains the GraphOS system currently implemented under `backend/algent_backend/graph_os/` in exhaustive detail:

- how state is modeled
- how mutations flow through the system
- how commits are serialized, hashed, and persisted
- how validation/invariants are enforced
- how integrations (especially Algo Lab) produce graph data
- what is production-usable vs placeholder/projection scaffolding
- what capabilities and constraints exist today
- review findings and risks discovered from code and tests

This is a code-grounded document (implementation-first), not just a vision summary.

## What GraphOS Is (Today)

GraphOS is an event-sourced workspace graph substrate with:

- typed IDs for workspaces/nodes/edges/ops/commits
- graph primitives (`Node`, `Edge`, `Layout`, `Snapshot`)
- a small GraphOps mutation language (`CreateNode`, `SetNodeProps`, `CreateEdge`, `SetLayout`)
- a reducer (`apply_ops`) with optimistic version checks
- a vocabulary registry with node/edge type constraints
- a filesystem commit ledger (`CommitLedgerStore`) as the durable source of truth
- a service entrypoint (`GraphOSService`) for dry-run and commit flows
- integration code that converts Algo Lab experiment results into GraphOps bundles

The implemented source of truth is a commit ledger on disk, not an in-memory graph and not SQLite (SQLite is scaffolded but not implemented).

## Status Summary (Implemented vs Scaffolded)

### Implemented and test-backed

- Core IDs, errors, primitives, invariants
- GraphOps serialization/deserialization
- Reducer (`apply_ops`)
- Vocabulary validation (`validate_ops`, algo-lab vocab pack)
- Commit hashing and canonical commit serialization
- Filesystem append-only commit ledger with replay and integrity checks
- Workspace file lock (`.lock`)
- `GraphOSService` mutation/read entrypoint
- Agent tool shim (`apply_graph_ops_tool`)
- Algo Lab run-record GraphOps integration
- Kernel and vocab tests (mostly passing)

### Present but minimal / placeholder

- Query service (`nodes_by_kind` only)
- Lineage service (simple payload filtering)
- Export service (counts-only JSON export)
- RDF projection/export/SHACL modules (placeholder)
- RAG projection/index/store adapters (placeholder)
- SQLite store implementation (interface stub only)
- SQLite migrations (placeholder SQL comments)

## Package Topology

`graph_os/` is organized by architecture layers:

- `core/`: primitives, IDs, errors, commit serialization, invariants, vocabulary model/rules
- `graphops/`: mutation operation types, reducer, validation, replay, checkpoints
- `persistence/`: store interface + filesystem ledger + lock + future sqlite store
- `services/`: high-level access layer (`GraphOSService`) plus query/lineage/export helpers
- `integration/`: adapters that translate external domain actions into GraphOps
- `projection/`: rebuildable derivatives (RDF / RAG), mostly placeholders
- `state/`: small enums/helpers for lifecycle/concurrency concepts
- `docs/`: design intent and kernel constitution

This is structurally sound: kernel concerns are mostly isolated from integration/projections.

## Core Domain Model

### Typed IDs (`core/ids.py`)

GraphOS uses wrapper dataclasses around UUID strings:

- `WorkspaceId`
- `NodeId`
- `EdgeId`
- `OpId`
- `CommitId`

Key behaviors:

- IDs are normalized to UUID hex (hyphens removed)
- constructors accept `UUID` or string
- invalid/empty values raise immediately
- `.new()` creates random UUID4 hex

This gives stable opaque identity and prevents accidental free-form IDs.

### Primitives (`core/primitives/*`)

#### `Node`

- `node_id`, `kind`, `props`
- `created_at`, `updated_at`
- mutable dataclass with `clone()`

#### `Edge`

- `edge_id`, `edge_type`, `src`, `dst`, `props`
- `created_at`, `updated_at`
- mutable dataclass with `clone()`

#### `Layout`

Presentation metadata keyed by `node_id`:

- `x`, `y`, `width`, `height`
- optional `group_id`
- optional `parent_workspace_id`
- `created_at`, `updated_at`

#### `Snapshot`

Workspace state materialization:

- `workspace_id`
- `nodes: Dict[str, Node]`
- `edges: Dict[str, Edge]`
- `layouts: Dict[str, Layout]`
- `vocab_version` (currently unused by reducer/service)
- `graph_version` (optimistic concurrency counter)

Important detail:

- `Snapshot` is conceptually treated as immutable by the reducer API, but implementation uses `clone()` and mutates the clone. This is a pragmatic copy-on-write style.

## Invariants and Error Model

### Errors (`core/errors.py`)

Hierarchy:

- `GraphOSError` base
- `GraphInvariantError` for logical/state violations
- `VocabularyError` (defined but not actively used in current flow)
- `VersionMismatchError` for optimistic concurrency mismatch
- `CommitIntegrityError` for hash chain/sequence corruption
- `WorkspaceLockError` for lock contention

### Snapshot invariants (`core/invariants.py`)

`verify_snapshot(snapshot)` enforces:

- non-negative `graph_version`
- node dict key matches each `Node.node_id`
- edge dict key matches each `Edge.edge_id`
- all edge endpoints exist
- layout dict key matches each `Layout.node_id`
- all layouts refer to existing nodes

This runs after `apply_ops(...)` finishes the op batch.

## GraphOps Mutation Language

### Implemented op types (`graphops/op_types.py`)

Base op:

- `GraphOp(op_id, actor, expected_version, timestamp)`

Concrete ops:

- `CreateNode`
- `SetNodeProps`
- `CreateEdge`
- `SetLayout`

Each op has:

- a stable `op_type` string
- `payload()` for op-specific data
- `to_dict()` serialization
- `from_dict()` deserialization

`GraphOpRegistry` maps `op_type -> class` for decoding.

### Op serialization

`serialize_op(op)` and `deserialize_op(payload)` are the canonical op converters used by commit serialization and replay.

Notable behavior:

- op timestamps serialize via `datetime.isoformat()`
- `SetLayout` normalizes numeric fields to floats in `__post_init__`

## Reducer Semantics (`graphops/op_apply.py`)

`apply_ops(snapshot, ops)` is the mutation engine.

### Execution model

1. Clone input snapshot
2. For each op in order:
   - require `op.expected_version == working_snapshot.graph_version`
   - dispatch by op type
   - mutate the working snapshot
   - increment `graph_version`
3. Run `verify_snapshot`
4. Return new snapshot

### Reducer guarantees

- deterministic given same input snapshot + op sequence
- no silent last-write-wins for version mismatches
- preserves append-order semantics

### Op behaviors

#### `CreateNode`

- fails if node already exists
- inserts node with timestamp as both `created_at` and `updated_at`

#### `SetNodeProps`

- fails if node missing
- shallow-updates `node.props`
- updates `updated_at`

#### `CreateEdge`

- fails if src/dst nodes are missing at execution time
- fails if edge already exists

#### `SetLayout`

- fails if node missing
- upserts layout record
- preserves original `created_at` on overwrite

## Validation Layers (Before Reducer)

### `validate_ops(...)` (`graphops/op_validate.py`)

Validation is split from reducer execution.

It currently performs:

- duplicate `op_id` detection within the proposed batch
- vocabulary validation for `CreateNode`
- vocabulary validation for `CreateEdge`

If a `snapshot` is supplied:

- existing node kinds are loaded from snapshot
- `CreateNode` ops pre-populate a temporary `node_kinds` map for edge-kind validation

If a `vocab` is supplied:

- `CreateNode` -> `validate_node(...)`
- `CreateEdge` -> `validate_edge(...)`

### Important architectural distinction

`validate_ops` checks semantic compatibility (types, required props, allowed edge endpoints), while `apply_ops` checks execution-time state mechanics (existence, duplicates, version order, invariants).

This separation is good architecture, but it introduces a current mismatch (see Review Findings) when validation is more permissive than reducer ordering.

## Vocabulary System (Semantic Constraints)

### Type model (`core/vocab/types.py`)

- `PropertySpec`
- `NodeKind`
- `EdgeType`

Definitions include descriptions and required/optional property specs.

### Registry (`core/vocab/registry.py`)

`VocabularyRegistry` stores:

- `version`
- `node_kinds`
- `edge_types`

Global access pattern:

- module-global `_DEFAULT_REGISTRY`
- lazy loading of packs via `_load_default_packs()`
- `get_registry()` returns the shared registry instance

### Rules (`core/vocab/rules.py`)

`validate_node(...)`:

- rejects unknown node kind
- checks required props presence

`validate_edge(...)`:

- rejects unknown edge type
- requires known source and destination kinds
- enforces allowed src kind and dst kind constraints
- checks required edge props (if any)

Current validation scope is presence/compatibility only; property value type enforcement is not implemented yet (even though `PropertySpec.value_type` exists).

### Default vocabulary pack (`core/vocab/packs/algo_lab.py`)

Implemented node kinds include:

- `lab.algo`
- `lab.algo.experiment`
- `lab.algo.run`
- `lab.algo.artifact.metrics_timeseries`
- `note`

Implemented edge types include:

- `contains`
- `has_run`
- `produces`
- `annotates`
- `compares_to`

This makes GraphOS immediately usable for Algo Lab run lineage and annotations.

## Commit Model and Ledger Integrity

### Commit object (`core/commit.py`)

`Commit` fields:

- `workspace_id`
- `commit_id`
- `seq`
- `base_version`
- `actor`
- `timestamp`
- `ops`
- `prev_commit_hash`
- `commit_hash`
- optional `message`
- optional `tags`

### Canonicalization and hashing

The commit hash is SHA-256 over a canonical JSON payload that excludes `commit_hash` and includes:

- workspace + commit identity
- sequencing metadata
- actor
- timestamp
- op list (serialized)
- previous hash
- optional message/tags (when present)

Key details:

- JSON uses sorted keys + compact separators
- timestamps are normalized to UTC in commit serialization helpers
- `build_commit(...)` computes hash and returns immutable `Commit` with `commit_hash`
- `deserialize_commit(..., verify_hash=True)` recomputes and verifies hash on load

### Why this matters

This provides:

- tamper detection
- deterministic replay inputs
- append-chain integrity
- auditability without a database transaction log

## Persistence: Filesystem Commit Ledger (Primary Store)

### Store interface (`persistence/store_interface.py`)

`WorkspaceStore` protocol defines:

- `load_state(workspace_id) -> WorkspaceLedgerState`
- `append_commit(commit)`
- `workspace_lock(workspace_id)`

`WorkspaceLedgerState` carries:

- normalized `workspace_id`
- replayed `snapshot`
- `next_seq`
- `head_hash`
- `seen_op_ids` (for global op-id uniqueness)

### `CommitLedgerStore` (`persistence/filesystem/commit_ledger_store.py`)

This is the real durable backend today.

Directory layout:

- `<root>/workspaces/<workspace_id>/commits/00000001.json`
- `<root>/workspaces/<workspace_id>/.lock`

#### `load_state(workspace_id)`

Behavior:

- normalizes workspace ID
- ensures commits dir exists
- starts from `Snapshot.empty(workspace)`
- scans commit files (numeric `*.json`, ignores temp files)
- for each commit file:
  - parse JSON
  - deserialize + verify commit hash
  - verify workspace ID matches directory
  - verify commit sequence matches filename and expected next sequence
  - verify `prev_commit_hash` matches replay head
  - `apply_ops(snapshot, commit.ops)`
  - update `head_hash`, `next_seq`
  - index `op_id`s and reject duplicates across ledger

This makes replay the authoritative rebuild path.

#### `append_commit(commit)`

Behavior:

- verifies commit file for `seq` does not already exist
- checks expected next sequence from directory contents
- checks `prev_commit_hash` against current head file hash
- serializes commit
- writes via temp file + flush/fsync + `os.replace(...)`
- fsyncs directory best-effort

This is a strong filesystem-first append pattern.

#### Integrity features implemented

- hash verification during read
- sequence gap detection
- hash-chain verification
- duplicate `op_id` detection across full workspace history
- atomic visible commit files (temp -> rename)
- tmp-file filtering during replay

### File lock (`persistence/filesystem/lock.py`)

`WorkspaceFileLock` uses atomic create (`O_CREAT | O_EXCL`) on `.lock`.

Lock payload records:

- `pid`
- acquisition timestamp (UTC ISO string)

Behavior:

- entering an existing lock raises `WorkspaceLockError`
- releasing removes the lock file

Operational note:

- no stale-lock auto-recovery exists; stale locks require manual cleanup after crashes.

## Service Layer: The Canonical Entry Point

### `GraphOSService` (`services/graph_os_service.py`)

This is the mutation boundary and the intended API other subsystems should call.

#### `get_snapshot(workspace_id)`

- loads and replays ledger via store
- returns snapshot materialization

#### `dry_run_ops(workspace_id, ops)`

- loads current state
- validates batch + duplicate-op check against committed ledger
- applies ops in memory
- returns resulting snapshot without persisting

#### `commit_ops(workspace_id, ops, actor, message=None, tags=None)`

Flow:

1. acquire workspace lock
2. load current ledger state (replay)
3. `_prepare_ops(...)`:
   - `validate_ops(...)` against current snapshot + vocab registry
   - reject duplicate op IDs already committed
4. reducer apply (`apply_ops`)
5. `build_commit(...)` with next sequence / base version / head hash
6. `store.append_commit(commit)`
7. return new snapshot

This creates a single-writer, optimistic-versioned, event-sourced mutation contract.

### `_prepare_ops(...)` details

Validation today includes:

- vocab/rule checks using `get_registry()`
- duplicate `op_id` in batch (via `validate_ops`)
- duplicate `op_id` against historical ledger (service-level check)

If any errors exist, a single `GraphInvariantError` is raised with `;`-joined messages.

## Mutation Lifecycle (End-to-End)

This is the actual write path, expressed holistically:

1. Caller constructs GraphOps with explicit IDs, timestamps, actor, and sequential `expected_version` values.
2. Caller submits batch to `GraphOSService.commit_ops(...)`.
3. Service acquires workspace lock.
4. Store replays the entire ledger to reconstruct authoritative snapshot/head/op-id set.
5. Service validates ops against vocabulary and historical op IDs.
6. Reducer applies ops in-order against snapshot with per-op version checks.
7. Service builds immutable commit payload containing the op batch.
8. Store atomically appends commit file to ledger.
9. Updated snapshot is returned to caller.
10. Future reads rebuild from ledger and must produce the same snapshot.

This is structurally strong because every stage has a narrow responsibility and explicit failure mode.

## Integrations and Domain Adapters

### Agent tool shim (`integration/agent_tools/graph_os_tools.py`)

`apply_graph_ops_tool(...)` wraps `GraphOSService` for agent-facing usage:

- supports `dry_run=True`
- passes through optional commit `message` and `tags`
- returns compact result `{status, graph_version}`

This is the current bridge between an agent tool interface and the kernel.

### Algo Lab run-record adapter (`integration/labs/algo_lab_run_records.py`)

This is the strongest example of GraphOS usage in the repo.

#### What it does

Transforms an `ExperimentResult` into a GraphOps bundle that can create:

- Algo Lab root node (`lab.algo`)
- experiment node (`lab.algo.experiment`)
- run node (`lab.algo.run`)
- metric artifact nodes (`lab.algo.artifact.metrics_timeseries`)
- connecting edges (`contains`, `has_run`, `produces`)

#### Important design choices

- uses `base_version` to assign sequential `expected_version` values in the generated batch
- emits deterministic op ordering for the created structures (except caller can choose optional creation flags)
- metric artifacts include `source_run_id`
- artifact payloads use serialized metric JSON (`data`)

#### Snapshot-aware generation

`build_run_record_ops_from_snapshot(...)` checks whether provided node IDs already exist in the snapshot to avoid recreating them.

#### End-to-end helper

`run_sorting_and_commit(...)`:

- runs Algo Lab sorting experiment
- reads current snapshot
- builds GraphOps
- commits via `GraphOSService`
- returns the experiment result

This demonstrates GraphOS as a persistence/lineage substrate for lab workflows.

## Query, Lineage, and Export Services (Current State)

### `GraphQueryService`

Currently implemented:

- `nodes_by_kind(kind)` -> list of matching nodes

Limitations:

- no edge traversal
- no filtering on props
- no pagination/indexing
- no workspace store integration (operates on a provided snapshot only)

### `GraphLineageService`

Currently implemented:

- stores in-memory list of `LineageEntry`
- `history(node_id)` filters entries where `op_payload["node_id"] == node_id`

Limitations:

- does not inspect edge `src`/`dst`
- no commit-level lineage reconstruction
- no integration with commit ledger loader

### `GraphExportService`

Currently implemented:

- `export_json(snapshot)` returns counts and metadata only

It is a diagnostic summary, not a full graph export.

## Projections (RDF / RAG): Architectural Hooks, Mostly Scaffolding

### RDF projection (`projection/rdf/*`)

Implemented pieces:

- `rdf_mapping.py`: maps node kinds / edge types to IRIs (`https://algent.dev/graph/...`)
- `rdf_export.py`: placeholder returning `rdf://workspace/<id>`
- `shacl_validate.py`: placeholder returning `[]`

Interpretation:

- the package layout is architecturally correct
- actual semantic projection/export/validation is not implemented yet

### RAG projection (`projection/rag/*`)

Implemented pieces:

- `rag_store_interface.py`: protocol (`add`, `search`)
- `rag_textify.py`: `node_to_text(snapshot, node_id)` basic stringification
- `rag_indexer.py`: no-op iterator placeholder
- `stores/faiss_store.py`: placeholder adapter
- `stores/sqlite_fts_store.py`: placeholder adapter

Interpretation:

- extension seams exist
- no durable or searchable index implementation is active yet

## State and Concurrency Support Modules

### `state/concurrency.py`

- `VersionVector(workspace_version)`
- `bump()` method

Currently not wired into the commit pipeline (the reducer/service use scalar `graph_version` on `Snapshot` + per-op `expected_version`).

### `state/workspace_state.py` and `state/op_commit_state.py`

Enums for conceptual lifecycle states:

- `WorkspaceState`: `ACTIVE`, `LOCKED`, `MIGRATING`
- `OpCommitState`: `APPLYING`, `COMMITTED`, `FAILED`

Currently declarative; not integrated into runtime orchestration.

## CLI Workflows (Operational Entry Points)

### `cli/run_algo_lab.py`

Provides a minimal end-to-end workflow:

- run sorting experiment
- generate GraphOps from result
- commit to GraphOS ledger
- print workspace/run/artifact info

Default store root:

- `Path.cwd() / ".graphos"` unless `--store-root` provided

### `cli/list_algo_runs.py`

Reads GraphOS snapshot and lists `lab.algo.run` nodes:

- sorts by `created_at`
- parses run params JSON
- finds artifact outputs via `produces` edges

This proves GraphOS snapshots are usable for downstream read APIs/CLIs today.

## Testing Coverage and What It Proves

### Kernel tests (`backend/tests/test_graph_os_kernel.py`)

Covers:

- reducer builds snapshots correctly
- sequential version enforcement
- snapshot invariant detection
- service commit + reload consistency
- deterministic replay
- tmp commit file ignore behavior
- tamper detection (commit hash mismatch)
- duplicate op-id rejection across commits
- commit sequence gap detection
- agent tool shim commit path

### Vocabulary tests (`backend/tests/test_graph_os_vocab.py`)

Covers:

- unknown node kind rejection
- missing required prop rejection
- invalid edge kind combination rejection
- intended edge validation order-independence (currently failing due reducer mismatch)

### Algo Lab integration tests (`backend/tests/test_algo_lab_run_records.py`)

Covers:

- canonical JSON stability
- run-record commit and replay
- presence of run/artifact nodes and edges (`has_run`, `produces`)

## Capabilities Matrix (Today)

### Strong capabilities

- Append-only audited graph mutation history
- Deterministic replay to snapshot
- Hash-chained commit integrity checks
- Typed semantic vocabulary validation (presence + edge endpoint compatibility)
- Optimistic concurrency via `expected_version`
- Workspace single-writer lock
- Agent/lab integration path via GraphOps

### Partial capabilities

- Querying (basic kind filter only)
- Export (summary only)
- Lineage inspection (manual/in-memory only)
- Alternate stores (SQLite scaffold only)

### Planned/architected but not implemented

- Full RDF projection and SHACL validation
- RAG indexing/search
- Rich structured query/traversal API
- Incremental projections off commit deltas
- Snapshot/checkpoint acceleration

## Architectural Strengths

1. Strong kernel boundary

- Core primitives, reducer, commit serialization, and store are cleanly separated from adapters/projections.

2. Determinism-first write path

- Explicit IDs/timestamps/versions live in ops; replay reconstructs state.

3. Integrity-aware persistence

- Hash chain + seq/file checks + atomic append give robust filesystem semantics.

4. Semantic discipline without overfitting

- Vocabulary registry constrains kinds/edges while staying lightweight.

5. Good extension seams

- `services/`, `integration/`, `projection/`, and store protocol make future growth tractable.

## Review Findings (Code-Level)

### 1) Confirmed behavior mismatch: edge validation is order-independent, reducer execution is not

`validate_ops(...)` pre-populates node kinds from all `CreateNode` ops before validating `CreateEdge`, so an edge can pass semantic validation even if the referenced nodes are created later in the same batch. However, `apply_ops(...)` executes strictly in sequence and `CreateEdge` fails immediately if endpoints are not yet in `snapshot.nodes`.

Impact:

- a batch may pass service `_prepare_ops(...)` but still fail in reducer apply
- test `test_edge_validation_is_order_independent` currently fails
- semantic validation contract and execution contract disagree

This should be resolved either by:

- enforcing execution-order validation in `validate_ops`, or
- topologically reordering ops before reducer apply (less desirable unless explicitly designed), or
- extending reducer semantics to support deferred edge materialization (complex)

### 2) `Snapshot.vocab_version` exists but is not managed or enforced

The snapshot type includes `vocab_version`, but current commit/replay/service flows do not set or validate it.

Impact:

- no explicit linkage between committed graph state and vocabulary version
- hardening/migration of vocab may become ambiguous later

### 3) Service/query/export/lineage names imply richer functionality than current implementations

`GraphQueryService`, `GraphLineageService`, and `GraphExportService` are present but minimal. This is not incorrect, but it is important for downstream consumers to know these are thin stubs, not feature-complete services.

Impact:

- risk of over-assuming capabilities when wiring UI/agents
- future work should either expand them or clearly annotate them as placeholder services

## Recommended Next Hardening Steps (High Value)

1. Resolve validator/reducer ordering mismatch

- make validation and execution contracts match exactly

2. Add property type validation in vocab rules

- `PropertySpec.value_type` is defined but not enforced

3. Persist and validate `vocab_version`

- commit-level or snapshot-level tagging will support future schema evolution

4. Implement a real query/lineage API over `WorkspaceStore`

- even basic traversals and provenance from commit ledger would unlock agent usage

5. Add checkpoint/materialized snapshot strategy

- replay-on-every-read is correct but will degrade with ledger growth

## Practical Mental Model (Holistic to Concrete)

GraphOS is best understood as three layers:

1. Kernel (truth + physics)

- IDs, primitives, GraphOps, reducer, invariants, commits, ledger

2. Semantic policy (grammar)

- vocabulary registry + rules for what kinds/edges are allowed

3. Adapters and projections (experience)

- Algo Lab record generation, CLI workflows, future query/export/RDF/RAG

The kernel is the strongest, most complete part of the system today. The semantic layer is useful and already constraining real data. The projection/query ecosystem is intentionally scaffolded and ready for expansion.

## Appendix: Key Files to Read First

For anyone maintaining or extending GraphOS, start here:

- `backend/algent_backend/graph_os/services/graph_os_service.py`
- `backend/algent_backend/graph_os/persistence/filesystem/commit_ledger_store.py`
- `backend/algent_backend/graph_os/core/commit.py`
- `backend/algent_backend/graph_os/graphops/op_apply.py`
- `backend/algent_backend/graph_os/graphops/op_validate.py`
- `backend/algent_backend/graph_os/core/vocab/packs/algo_lab.py`
- `backend/tests/test_graph_os_kernel.py`
- `backend/tests/test_graph_os_vocab.py`
- `backend/tests/test_algo_lab_run_records.py`

