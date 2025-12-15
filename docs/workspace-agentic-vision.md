# Agent-Editable Workspace OS

## One-Sentence Vision
A **graph-native workspace** where humans and AI agents co-build "walls of windows" atop an infinite canvas-each window is a persisted module, each connection is a typed relationship, and every mutation is logged as lineage so the work remains replayable, auditable, and evolvable.

## Graph Spine as Source of Truth
- Nodes are modules (Algo Lab, News Hub, Dataset, Run, Chart, Agent Session, Report, etc.).
- Edges are typed channels (data flow, control flow, lineage, semantic context).
- Every UI, dashboard, or timeline is a projection of the same Workspace Graph, never a parallel state.

## Canvas as View, Not Substrate
- An infinite pan/zoom wall of windows renders the graph spatially.
- Windows map to nodes; connectors reveal edges.
- Users/agents can toggle between Canvas View (spatial), Graph View (network), and Lineage View (historical evolution) without mutating the underlying graph.

## Shared Agent/Human Primitives
Both humans (drag/drop) and agents (tool calls) use shared ops.

**Graph Ops**
- `node.create(type, props)`
- `node.update(node_id, patch)` / `node.delete(node_id)`
- `edge.create(from, to, kind, props)` / `edge.delete(edge_id)`

**Layout/View Ops**
- `layout.set(node_id, x, y, w, h)` to place canvas windows.
- `group.create(node_ids)` / `group.collapse(group_id)` to frame and cluster work.
- `viewport.set(center, zoom)` so agents can "navigate" the wall.

## What "Agent Builds the Wall" Means
Example prompt: *"Run a parameter sweep and show the best curves."*
1. Agent spawns an Algo Lab node and a Batch/Sweep node beside it.
2. Links them with control+data edges.
3. Executes runs; creates Run nodes plus result artifacts.
4. Spawns Chart nodes, wiring them to the relevant runs.
5. Wraps top-performing artifacts into a collapsible frame and leaves notes/commit.
The output is a coherent research desk, not a pile of files-everything sits on the graph spine.

## Infinite Scalability via Semantic Zoom
- Zoomed out: groups collapse into single tiles, edges aggregate ("12 links").
- Mid zoom: windows show summaries, statuses, and key controls.
- Deep zoom: full charts, logs, and parameter editors.
- Nested workspaces: any node can encapsulate a child graph (canvas-in-canvas) so meta-modules and micro-modules coexist without spaghetti.

## Lineage, History, and Replay
- Every graph mutation appends to a log with who/what/why/when.
- Enables true undo/redo, time travel ("show workspace pre-run-27"), branching experiments, and audit trails for every artifact.

## Labs as Pluggable Node Types
- Each lab publishes a manifest (actions, inputs/outputs, parameters).
- UI auto-renders controls; agents can introspect capabilities.
- Algo Lab, News Hub, Data Lab, Memory Lab, etc. become first-class nodes living on the same graph substrate.

## North Star Slice
1. Drop an Algo Lab node.
2. Run an experiment -> creates a Run node plus metrics artifact.
3. Auto-spawn a Chart node wired to the run.
4. Allow agents to perform steps 1–3 solely via graph ops.
5. Persist/reopen the workspace with full lineage intact.

Delivering this slice proves the graph spine, agent-editable workspace, and wall-of-windows experience.
