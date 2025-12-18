# GraphOS Kernel Constitution

## Purpose

GraphOS is a graph-native substrate where **agents and humans share the same primitives** for building and evolving a workspace. The kernel defines the minimal “physics + grammar” required for a stable, replayable, and extensible graph system.

The kernel exists to guarantee **reliability, determinism, and composability** as complexity scales.

## Kernel Boundary

**Kernel** means: **core primitives + GraphOps (mutation contract) + invariants/validation + deterministic serialization/replay rules**.

Anything outside this boundary (UI renderers, lab logic, indexing, search, metrics, embeddings, RDF exports, checkpoints, etc.) is a **projection** or **integration** and must not redefine canonical truth.

## Canonical Truth

GraphOS has exactly one source of truth:

**The canonical commit ledger is authoritative.**

All durable changes to the graph must be represented as GraphOps packaged inside an immutable commit file and appended to the ledger. "Current state" snapshots may exist, but only as **derived** materializations of the ledger.

### Commit Law

* A commit is the smallest atomic unit of history. It contains {workspace_id, commit_id, seq, base_version, actor, timestamp_utc, ops[], prev_commit_hash, commit_hash} plus optional message/tags metadata for later UI.
* seq is monotonically increasing and must match the filename commits/00000042.json.
* Commit payloads are serialized via a single canonical encoder (sorted keys, ISO-8601 UTC Z timestamps, stable op ordering) and hashed with SHA-256 over the payload **excluding** commit_hash but **including** prev_commit_hash, seq, and every op dict.
* The ledger is append-only. Commit files are written via 	mp -> flush/fsync -> atomic rename. Once visible they are immutable forever.
* Hash chaining is mandatory. Replay verifies that every prev_commit_hash matches the predecessor's commit_hash and recomputes the hash byte-for-byte. Any mismatch or gap terminates replay immediately.
* Global op_id uniqueness is enforced: an op_id may only appear once in the entire workspace history.
* The only authorized mutation entrypoint is GraphOSService.commit_ops. Reducers and stores are internal. Integrations may only call GraphOSService.dry_run_ops (read) or GraphOSService.commit_ops (write).

## Determinism

Applying a sequence of GraphOps to an initial empty state must deterministically produce the same canonical graph state.

Practically:

* **All entropy lives inside ops** (IDs, timestamps if used, seeds if randomness matters).
* There is exactly one canonical serializer/decoder for commits and ops (sorted keys, ISO timestamps with Z, deterministic ordering). Anyone writing commits must use it.
* Replay must never depend on "now," hidden randomness, unordered iteration, or environment-specific side effects.

## Ops-Only Mutation

No subsystem (UI, labs, agents, services) is allowed to mutate canonical graph state directly.

The only legal write-path is:

**propose ops + validate + apply + build commit + append to ledger + return updated state/diff**

If you need a "fast path," it must still end as GraphOps.

## Invariants

The kernel enforces “physics invariants” that prevent corrupted state.

At minimum:

* IDs are unique and well-formed (node/edge IDs within a workspace and op_id across the entire ledger).
* Edges cannot point to missing nodes.
* Ops must be valid for the current graph version (no silent conflicts).
* Canonical state must remain internally consistent after every commit.

Higher-level meaning rules (schemas, allowed edge types between node kinds, required fields, etc.) belong to the **vocabulary layer** and are versioned, not ad hoc.

## Identity

Every entity has a stable internal identity:

* **Internal ID**: opaque, immutable, globally unique within a workspace graph.
* **External identity (optional)**: semantic identifiers or references used for integration, merging, RDF mapping, or cross-workspace linking.

Internal IDs are never reused. External identity is allowed to evolve, be missing, or be refined over time.

## Workspace Ownership and Nesting

* A workspace owns exactly one canonical ledger directory (workspaces/<workspace_id>/commits/).
* Nested graphs or linked workspaces must be represented via explicit references (for example, a node property that stores another workspace_id).
* Internal IDs are only meaningful inside their workspace. Cross-workspace links must use explicit references or external identifiers.

## Properties and Vocabulary

The kernel supports flexible properties, but **prevents semantic chaos** by requiring a vocabulary discipline:

* Node/edge “kinds” and edge “types” come from a registry (even if permissive early).
* The vocabulary may start loose, but must be able to harden over time via versioned definitions.
* Agents may propose new vocabulary entries, but vocabulary changes are explicit operations, not implicit drift.

## Granularity Policy

GraphOps represent **meaningful intent**, not raw UI telemetry.

Layout/view changes may be persisted, but should be committed as coarse “end-of-interaction” ops (e.g., drag-end), not pixel-by-pixel streaming. Canonical history should remain readable and replayable at scale.

## Projections, Caches, and Derived Systems

Anything that can be regenerated from canonical state is a **projection** (or cache) and is never allowed to become a second truth.

Examples: materialized snapshots, checkpoints/head pointers, search indices, RAG vector indices, RDF exports, metrics, thumbnails, UI caches.

If a projection disagrees with canonical state, the projection is wrong and must be rebuilt.

## Concurrency and Ordering

The canonical ledger defines a single total order of committed ops (monotonically increasing sequence numbers with no gaps).

Concurrency is resolved explicitly via optimistic version checks and a single-writer lock per workspace. Each workspace exposes workspaces/<id>/.lock, acquired via atomic create. The lock stores {pid, timestamp} and must be released (or manually cleared after a crash) before another writer proceeds. There is never a silent last-write-wins behavior that would undermine determinism.

Snapshots, checkpoints, indices, and head pointers are **projections**. Deleting them never harms canonical truth because the ledger is sufficient to rebuild deterministically.

## Compatibility Commitments

GraphOS is designed LPG-first but must remain compatible with future “hardened semantics”:

* RDF/ontology and rule/inference layers may be added as projections or overlays.
* RAG may index graph slices and artifacts, but retrieval must map back to canonical IDs.
* Export/import must preserve identity and meaning to the extent possible.

These additions must never weaken kernel determinism or canonical truth.

## Testing and Non-Regression

Kernel behavior is treated as load-bearing infrastructure.

Every new op type or invariant requires tests that prove:

* deterministic replay
* invariant preservation
* canonical serialization stability (where applicable)
* conflict handling (version checks)

Breaking kernel contracts requires an explicit versioned migration plan.
