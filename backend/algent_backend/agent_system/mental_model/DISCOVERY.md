# Discovery

How a story gets *found* — everything before anyone researches or writes one.

## The shape

Discovery is a **data pipeline followed by two agents**, not one agent that goes
looking:

```text
t0   ingest pipeline   source channels -> a scored, deduped pool of candidates
t1   discovery_synthesis  pool -> a ResearchPortfolio of research vectors
     signal_router        portfolio -> the one vector promoted to research
```

The t0 half is deterministic code (`data_ingestion/newsroom/discovery/`), not a
model loop. That is the important structural fact: **candidate acquisition is
plumbing, judgment is the agent's**. Fetching, pacing, deduping and echo
suppression are mechanical problems with mechanical answers, and a model asked to
do them does them worse and unpredictably.

## t0 channels

Toggleable, resolved by `resolve_channels` (arg -> `ALGENT_T0_CHANNELS` -> all):

| channel   | source                          | role |
|-----------|---------------------------------|------|
| `gkg`     | GDELT GKG net                   | what the world's press is actually covering |
| `beats`   | rotating GDELT DOC sweep        | the **diversity channel** — deliberate breadth |
| `markets` | Polymarket                      | where money disagrees with consensus |
| `x`       | X API                           | first-party and fast; pre-vetted, bypasses the rake |
| `science` | curated RSS/Atom journal feeds  | the beat the news wires structurally underserve |

`beats` is the one most easily lost and most costly to lose — it is usually the
largest single contributor, and it is the reason the pool is not just today's
wire cycle. It sweeps against GDELT DOC, which enforces a **shared, stateful,
escalating rate limit**: anything else that hits DOC unpaced beforehand will make
the sweep fail wholesale with `rate_limited` and zero hits. A beat channel
returning nothing is nearly always that, and nearly never the beats being dead.

## Why there is no "discovery agent" to launch

There used to be: `general_discovery`, a ReAct agent that improvised GDELT DOC
queries from a prompt. It is **retired**. The t0 pipeline superseded it, nothing
in the newsroom rail called it, and leaving it registered was actively harmful —
it fired unpaced parallel DOC queries, so running it immediately before a sweep
429'd the limiter and emptied the beat channel.

Discovery starts at `ingest t0`. See `docs/guides/newsroom-pipeline.md` for which command produces
which outcome.

## What the agents add

- **`discovery_synthesis`** reads the pool and writes a `ResearchPortfolio`: a set
  of *research vectors*, each a thesis with key questions and the t0 item ids
  supporting it. This is the step that turns headlines into angles.
- **`signal_router`** ranks the portfolio and promotes one vector. Ranking is
  rut-discounted and cooldown-aware on purpose: an unweighted "best story" metric
  converges on the same few super-topics and quietly becomes the thing that
  destroys variety.

## Deferred

The rake layer for un-vetted channels, additional synthesis specialties, and
scheduling.
