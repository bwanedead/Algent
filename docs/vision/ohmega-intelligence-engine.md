# Ohmega Monster — the intelligence engine

> Canonical vision for what Ohmega is becoming. Architecture lives in
> `docs/architecture/pulse-system.md`; editorial doctrine lives in the newsroom's `spirit.md`.
> Extend this doc rather than starting a parallel one.

## What Ohmega is

Ohmega is not an AI news site. It is an **intelligence engine**: a system that continuously takes
in noisy external reality, pulls signal out of it, checks it, grades it, and keeps what it learns.
Articles are one output of that engine. They are not the engine.

The durable asset is the **accumulating model of the world** underneath the articles:

- **graded claims** (confirmed, likely, contested…) with sources, snapshots and as-of dates;
- **situations**: enduring subjects like Russia–NATO or China–Taiwan, which stories attach to;
- **Pulses**: persistent, auditable belief states about those situations, revised as evidence
  arrives, each with a full history of what moved it and why;
- **watches**: forward conditions whose outcomes teach the system how well it reads the world;
- a visible **corrections record**.

Prose is being commoditised. Graded, sourced, dated, revisable judgment is not.

## The loop

A media organisation does *observe → publish*. Ohmega does:

    observe → research → grade → update the model → publish → feed the result back into the model

Every article run leaves the model a little better informed. The next run starts from what we
already know instead of from zero. That is what makes the system **compound**: research gets
cheaper per article, judgments get steadier, and the history itself becomes valuable.

## The products are views onto one substrate

| Surface | For | What it shows |
|---|---|---|
| Articles | people | one story, researched, graded, readable |
| Headline radar | people | what crossed the wire today, clearly marked unverified |
| Pulse Gallery | people | the wall of Ohmega's current reads, with movement and confidence |
| Atlas (working name) | people | the geopolitics surface: situations on an off-axis globe |
| Agent API / MCP | AI agents | dossiers, claim checks, Pulse states, what changed |
| X | people | articles, the daily radar, and Pulse state changes |

The agent-facing product matters as much as the human one. Agents want the ledger, not the
prose: "what is established about X as of today, on what evidence, and how sure are you?"

## Principles that do not bend

1. **Legible trust, not borrowed authority.** Every reading shows how sure we are and how fresh
   it is. We say "Ohmega's current assessment", never "the truth". Unverified headlines can make
   a Pulse *stale*; only researched evidence can *move* it.
2. **Position, not mood.** A Pulse is a position on an anchored ruler, re-estimated each time,
   never a running sum of reactions to news. News over-reports escalation; the design must not
   inherit that.
3. **Nothing is overwritten.** Profiles, Pulse influences and corrections are append-only. The
   history of what Ohmega believed, and why, is part of the product.
4. **Self-audit.** Blind reassessments check whether our own priors have captured us. Watches
   check whether our forward reads were useful. Disagreement is a signal to surface, not hide.
5. **The reader's words.** Internal vocabulary (vectors, profiles, gauntlet) never reaches a
   reader. Neither does a source's regional idiom.
6. **Domain-agnostic machinery.** Geopolitics is the first domain. The same Situation/Pulse
   machinery must carry sports, markets or technology later without being rebuilt.

## For agents, today

Every published article has a machine-readable twin at `/data/articles/<slug>.json` (schema
`ohmega.article/1`: graded claims, citable sources only, corrections), indexed at
`/data/index.json` and described in `/llms.txt`. Source texts are never republished: we expose our
claims and link to theirs. Pulse states join this layer once the calibration period ends.

## Where it is going

- **Now:** the Pulse layer (situations, Pulses, events, watches) on a real database, seeded from
  the existing research corpus, running privately while it calibrates.
- **Next:** the Pulse Gallery, Pulse embeds in articles, the geopolitics surface, and a
  machine-readable twin of everything for agents.
- **Later:** an agent API and MCP server, calibration reports ("when we said severe, what
  happened?"), user-followed and user-authored Pulses, possibly Ohmega Sports on the same
  machinery, and eventually metered agent access once there is measured demand.

The phrase to keep in mind: **a continuously revised, provenance-bearing model of the world**,
with everything else a way of looking at it.
