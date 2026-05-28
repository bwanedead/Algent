# Modularity Ethos

This document complements `architecture-ethos.md` and `structural-ethos.md` by spelling out **how we decompose the system into modules** — how responsibilities are grouped, where files live, and how boundaries are drawn so the codebase stays navigable as it grows.

Where `architecture-ethos.md` says *separate concerns and avoid God objects*, and `structural-ethos.md` says *build weight-bearing layers*, this document is the practical grammar of **good decomposition**: high cohesion, low coupling, one home per responsibility, and directory structure that mirrors the system's real shape.

---

## 1. One Responsibility, One Home

Every responsibility should have exactly one canonical home.

- If you can't say in one sentence what a module is for, it is probably doing too much.
- If two modules both "kind of" own a responsibility, neither does — pick one and make the other depend on it.
- Shared concerns are genuinely shared (one implementation, imported), never copy-pasted into each consumer.

The test: a maintainer looking for *where X happens* should be able to guess the location, and be right.

---

## 2. Cohesion Over Convenience

Group things by **what they are about**, not by what they happen to be (a "type" of file).

- Prefer feature- and responsibility-oriented packages (`runs/`, `artifacts/`, `runtime/`) over technical buckets that collect unrelated things (`helpers/`, `utils/`, `misc/`, `common/`).
- A `utils.py` that accumulates unrelated functions is a monolith in disguise. If a helper has a clear owner, it belongs with that owner. If it is genuinely shared and cohesive, give it a named module that says what it is.
- When a folder's contents no longer share a theme, that is a signal to split it.

---

## 3. No Flat Dumping Grounds

A top-level domain package is a namespace, not a junk drawer.

- Do not scatter loose `.py` files directly inside a broad domain package (e.g. `agent_system/`). Each concern gets its own subpackage so the package's contents read as a map of responsibilities.
- A package's top level should contain `__init__.py` and subpackages — not a pile of sibling implementation files that only a historian could group.
- New features deserve their own dedicated directory. Do not wedge a new concern into an existing folder just because it was open.

If listing a directory does not communicate the system's shape, the structure has drifted.

---

## 4. Boundaries Are Contracts

Modules talk to each other through deliberate, stable surfaces — not by reaching into each other's internals.

- Expose a small, intentional public surface (via `__init__.py` exports or a clearly-public module). Treat everything else as internal.
- Consumers depend on the contract, not on incidental implementation details. Changing an internal should not ripple through the codebase.
- Prefer typed seams (explicit data contracts, protocols, ABCs) over duck-typed folklore that only works because the caller happened to know the shape.

A good boundary lets you rewrite the inside of a module without the outside noticing.

---

## 5. Dependency Direction Is Sacred

Dependencies should flow in one direction, toward stable contracts.

- Contracts and definitions depend on nothing internal; everything depends inward toward them.
- Avoid cycles. If two modules import each other, the responsibility split is wrong — extract the shared contract, or merge them.
- Volatile, swappable, or environment-specific pieces (adapters, providers, backends) live at the edges and are referenced through a single seam (a registry or factory), never imported ad hoc from the core.

The point of direction is that the core never has to change because an edge changed.

---

## 6. Size And Splitting Discipline

Files and modules should stay comprehensible.

- A file that has grown past easy reading is a prompt to ask *what distinct responsibilities are tangled here*, then split along those seams — not to add a section comment and move on.
- Split when a module accretes a second clear responsibility. Do **not** split prematurely into one-function files that fragment a single cohesive idea — over-fragmentation is its own form of unnavigability.
- Granularity is a judgment call: optimize for *fewest live shapes a reader must hold in mind*, not for an arbitrary line count.

---

## 7. Build For Extension, Not Prediction

Modular structure should make the *likely* next change local, without speculatively building for futures that may never come.

- It is enough that adding a new adapter, tool, or feature means adding a file in an obvious place — not editing the core.
- Resist erecting elaborate abstraction scaffolding before a second real use case exists. Two concrete cases reveal the right seam; one imagined case usually guesses wrong.
- When a deferred concern arrives, it should slot into a seam that already made sense — not require reorganizing what was already built.

Good modularity is proven by additions that are boring, local, and obvious.

---

### Summary

**"One home per responsibility. Group by purpose, not by type. Namespaces, not junk drawers. Depend inward. Split on seams, not on impulse."**
