# Graph Substrate Ethos

These principles ensure the workspace graph spine stays structurally sane as it evolves from LPG to hardened semantics, RDF projection, and RAG acceleration.

## 1. Truth lives in the GraphOps log
- Every mutation must be represented as an append-only GraphOp and replayable into the same state backed by the SQLite store.
- No subsystem is allowed to mutate the graph state without emitting GraphOps; projections (UI views, RDF exports, RAG indexes) subscribe to the log instead of writing ad hoc patches.

## 2. Identity and typing are sacred
- Node and edge IDs are assigned once and never recycled; names, titles, or layout metadata never drive identity.
- All nodes declare a registered `kind` and all edges declare a registered `type`; vocab registry updates are versioned artifacts.
- Consumers must validate inputs against the vocabulary service before persisting to avoid anonymous or misc entities.

## 3. Meaning, presentation, and lineage stay decoupled
- Semantic properties, layout metadata, and lineage events live in separate namespaces even when stored side by side.
- Any API that mutates presentation state must make it explicit (e.g., `layout.set` GraphOps) so semantic exports stay spotless.
- Lineage consumers (undo/redo, provenance inspectors) rely solely on the event log and never infer history from snapshots.

## 4. Derived insights are rebuildable
- Inferences, cached traversals, or precomputed metrics flag themselves as `derived=true` and include the source op/version they depend on.
- Rebuilding a derived layer from scratch must produce the same results; no derivation may be a "mystery truth" hidden in the base snapshot.

## 5. interfaces before implementation
- Graph service, vocabulary service, projection service, and indexing service interfaces are defined up front so teams can build against contracts instead of concrete classes.
- All new capabilities plug into those interfaces (or extend them intentionally) to prevent one-off pipelines that bypass the spine.

## 6. Incremental, observable operations
- Subsystems consume op deltas rather than rescanning full snapshots whenever possible, keeping the system responsive and debuggable.
- Each service logs what ops it processed and which artifacts it emitted so backfills and replay can be reasoned about with evidence.

## 7. Long-term resilience over quick wins
- Schema or graph changes must consider forward compatibility with RDF export, SHACL validation, and RAG indexing, even if those layers are not active yet.
- Tests and invariants live close to the domain (`core/invariants.py`, `tests/graph_os/...`) so regressions surface immediately; cover replay, idempotent ops, vocabulary validation, and semantic vs presentation separation to catch drift early.

Following this ethos ensures the graph substrate stays weight-bearing, auditable, and ready for the LPG -> ontology -> RDF -> RAG evolution without rewrites.
