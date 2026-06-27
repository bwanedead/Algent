# Newsroom test fixtures

Saved upstream artifacts so a pipeline stage can be run **in isolation** — without
re-running everything before it (no GDELT fetch, no fresh synthesis, no spend).

A run's `--input` *is* the graph's initial state, so feeding a fixture under the right
state key lets a stage consume supplied input instead of producing it. Use
`--input-file <fixture> --input-key <state-key>` on `runs start`.

## Fixtures

| file | what it is | feed to | state key |
|------|------------|---------|-----------|
| `t0_pool_sample.json` | a real t0 discovery pool (65 items: gkg + markets) | `discovery_synthesis` | `pool` |
| `t1_portfolio_sample.json` | a real t1 signal portfolio (31 vectors, with ids) | the router / profile lane | `portfolio` |

## Examples

```bash
# Run synthesis+rake on a saved pool (skips ensure_t0 / GDELT entirely):
python -m algent_backend.cli.runs start discovery_synthesis \
    --input-file fixtures/t0_pool_sample.json --input-key pool

# (once built) Run the router on a saved portfolio, no synthesis needed:
python -m algent_backend.cli.runs start signal_router \
    --input-file fixtures/t1_portfolio_sample.json --input-key portfolio
```

## Accumulating more

Every run writes its artifacts under
`runs_data/<agent>/<NNNN>__<id>/artifacts/` (e.g. `t0_pool.json`,
`research_portfolio.json`). To bank a good one as a fixture, copy it here. Keep
fixtures small and curated — they're committed test assets, not a data dump.
