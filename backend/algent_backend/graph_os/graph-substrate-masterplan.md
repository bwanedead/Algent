Below is a "graph spine" plan that starts **LPG-first** (fast workspace OS), and is deliberately engineered so you can later "flip the cake" into a **hardened semantic layer (RDF)** and add **RAG** as a retrieval accelerator--without rewriting the product.

---

## Initial Scaffolding

GraphOS lives under `backend/algent_backend/graph_os/` with the following load-bearing modules:

- `core/` for pure primitives (ids, nodes, edges, layout, snapshots) plus vocab registry, rules, and invariants.
- `graphops/` defining the mutation language (op types, validators, reducer, log replay, checkpoints).
- `persistence/` providing the canonical store adapters (SQLite by default, filesystem aids for dev).
- `services/` exposing the only entry points other subsystems call (apply ops, traverse, lineage, export).
- `state/` and `integration/` keeping concurrency discipline and outward shims isolated from the core.
- `projection/` containing rebuildable layers such as RDF exporters and RAG indexers.

SQLite (stdlib `sqlite3`) is the default durable store and Pydantic (or dataclasses) enforces GraphOp shapes.

## The Genesis Form

### One canonical substrate: the Workspace Property Graph

From day one, the **workspace graph is the source of truth**.

It contains three families of information, kept **separate but linked**:

1. **Semantic Graph (meaning/work)**

* Nodes: experiments, runs, datasets, artifacts, notes, hypotheses, agents, tasks
* Edges: produces, derived_from, depends_on, summarizes, references, validates, compares

2. **Presentation Graph (views/layout)**

* Layout: positions, sizes, grouping, collapses, zoom frames, nested canvases
* View nodes: chart panels, tables, dashboards, "window shells" that render some semantic node(s)

3. **Lineage Log (history)**

* Append-only "GraphOps" events that describe *every* mutation
* This is your time-travel, replay, undo/redo, audit trail foundation

**Rule:** UI and agents never "edit the graph directly." They emit **GraphOps**.

---

## The Core Principles You Must Maintain (non-negotiable)

These are the design parameters that keep the future open.

### 1) Stable identity always

* Every node/edge has a stable ID (never derived from title)
* IDs never change; properties can change
* "Same thing" must resolve to the same ID inside a workspace

This is the seed of RDF-style identity discipline.

### 2) Typed everything (kinds are mandatory)

* Every node has `kind` (e.g., `lab.algo`, `run`, `artifact.chart`, `note`)
* Every edge has `type` (e.g., `produces`, `derived_from`, `views`, `annotates`)
* No anonymous edges, no "misc" links

This is what later becomes your ontology classes/predicates.

### 3) Vocabulary is a first-class artifact

You maintain a **Versioned Vocabulary Registry**:

* `NodeKind` definitions (required props, optional props, description)
* `EdgeType` definitions (allowed src kinds -> dst kinds, required props)
* Property key definitions (meaning, type, units where relevant)

**Important:** You do not need to perfect it early--just require registration. That prevents drift.

### 4) Separate meaning from presentation

Layout/view metadata is not "the meaning." Keep it in a separate store/namespace.
That lets you export pure semantics to RDF later without dragging UI junk.

### 5) Mutations are event-sourced

All changes become append-only events:

* makes lineage deterministic
* powers incremental indexing (RAG)
* powers incremental semantic projection (RDF)
* makes debugging sane ("why is this node here?" -> look at the ops)

### 6) Derived facts are never "mystery truth"

Any inference you introduce later must be:

* computed on demand, or
* materialized but tagged `derived=true` and rebuildable

This keeps the graph auditable and prevents hidden corruption.

---

## Evolution Plan: LPG -> Hardened Semantics -> RDF + RAG

### Phase 1: LPG Exploration (build the OS and collect semantics)

**Goal:** make the workspace *alive* and agent-editable.

You build:

* Graph storage (SQLite or file snapshot + op log)
* GraphOps API (create node, connect, set props, set layout, group, etc.)
* A minimal set of node kinds and edge types (enough to build Algo Lab runs -> charts -> notes)
* A "North Star slice" that proves the loop

You also quietly collect telemetry for ontology discovery:

* which kinds are created most
* which edge types appear
* which properties show up repeatedly
* which constraints are violated often

This is your "semantic wind tunnel."

### Phase 2: Ontology Discovery Hardening (freeze what emerged)

**Goal:** turn "what we did" into "what it means."

You do:

* Promote the successful emergent vocabulary into a formal "Core Ontology v1"
* Add real constraints:

  * required props
  * allowed edge connections
  * cardinality expectations ("run has exactly 1 experiment parent")
* Add a small inference set that improves ergonomics:

  * `produces` implies lineage lane edges
  * `summarizes` implies "related-to" traversal shortcuts
  * lab manifests imply "supports actions" edges

At this stage, your system becomes **self-consistent** and more "knowledge-like" while still being LPG-first.

### Phase 3: RDF Projection ("flip the cake" without rewriting)

**Goal:** get RDF superpowers without making RDF the live substrate.

You add an exporter that produces an RDF graph from the semantic subset:

* Map `NodeKind` -> RDF class IRIs
* Map `EdgeType` -> RDF predicate IRIs
* Map property keys -> RDF predicates
* Include provenance links to lineage events if you want

Now you can:

* run SHACL validation for strictness
* run OWL/rules inference if you want
* query the projection with SPARQL

But the source of truth is still LPG. RDF is a *lens*.

### Phase 4: RAG Index (semantic retrieval accelerator)

**Goal:** let agents search conceptually when they do not know exact IDs.

You build an indexer that listens to GraphOps events and updates embeddings for:

* node titles, descriptions, notes
* run summaries and "what changed" diffs
* artifact captions/metadata
* optional "neighborhood summaries" (node + adjacent edges summarized into text)

Every embedding record must include:

* `node_id` (stable pointer)
* `field`
* `version` / `op_id` (so you can refresh incrementally)

Now agents can do:

* RAG search to find candidate nodes ("that weird oscillation run")
* then use graph traversal to ground the result ("show lineage, related artifacts, upstream params")

RAG does not replace RDF--it makes discovery ergonomic.

### Phase 5: Combined Agent Reasoning Loop (the final synergy)

Agents use a layered strategy:

1. **Try structured graph queries** when there is a handle (IDs, types, lineage)
2. **Use semantic layer / constraints** to understand what is allowed/expected
3. **Use RAG** when there is ambiguity, fuzzy matching, or exploratory intent
4. **Optionally consult RDF projection** when you want inference/federation/semantic joins
5. **Mutate workspace via GraphOps** to build the next state

That is your "absorb and diffuse information into decisions" system.

---

## Required Spine Interfaces (design these early)

Even if you do not implement all of them yet, define them so everything plugs in cleanly:

### A) Graph Service (truth)

* `apply_ops(ops[]) -> result + new_version`
* `get_snapshot(workspace_id, version?)`
* `query_structured(...)` (basic filters + traversals)
* `get_lineage(node_id|edge_id|op_id)`

### B) Vocabulary / Model Service

* `register_kind(kind_def)`
* `register_edge_type(edge_def)`
* `validate_snapshot(snapshot) -> violations`
* `infer(snapshot) -> derived_edges/nodes` (optional early)

### C) Projection Service (future)

* `semantic_snapshot(snapshot) -> semantic_subset`
* `export_rdf(semantic_subset) -> rdf_graph`
* `run_shacl(rdf_graph)` / `run_reasoner(rdf_graph)` (later)

### D) Indexing Service (RAG)

* `index_delta(ops_since_last)`
* `search(text, filters?) -> node_ids + scores`
* `hydrate(node_ids) -> graph subgraph`

The key is: **all these are projections off the same op log + snapshot**, so you never fight sync wars.

---

## The "Design Rules" to maximize long-term performance

Performance at scale comes from the same choices:

* **Incremental everything**: projection and indexing run off op deltas
* **Stable IDs + canonical serialization**: easy caching, deterministic diffs
* **Indexes on edges** (in SQLite/Postgres): fast neighborhood queries
* **Derived layers are rebuildable**: you can reindex and reproject safely
* **Semantic zoom/nesting**: store "subworkspace" as a normal node that points to another workspace graph id

---

## One-sentence summary

Start with an **LPG workspace graph + event-sourced GraphOps** to build the living agent-editable OS fast, while enforcing **stable identity + typed vocabulary + separation of semantics/presentation**, so you can later **harden the discovered ontology**, project it to **RDF for inference/federation**, and maintain a continuously updated **RAG index** for fuzzy semantic retrieval--without rewriting the core.

If you want, next I can propose the exact minimal v1 **GraphOps set** and the first **Core Vocabulary Registry** (node kinds + edge types) so you can start implementing immediately while staying on this long-term track.
