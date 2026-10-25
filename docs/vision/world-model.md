# The world model: what the brain keeps (vision, 2026-10-25)

Operator's framing: we are building a brain that takes in the world and makes judgments. We have ~10 GB. The goal is the **highest compression of
reality** we can hold: high-signal, nuance-carrying, continually evolving, judged by **predictive ability**, not by officialness. "Official" is
one actor's claim with its own incentives. A good model keeps the space of explanations open where the truth isn't known, without leaning into
one. Two people seeing the same news reach different conclusions because they run different world models; the model is the product.

## Principles
1. **Observations ≠ interpretations.** We store *who claimed what, when, and with what incentive*, never "what is true". A state statement, a
   wire story and a ship track are all observations with a source.
2. **Competing hypotheses per situation.** Each situation holds an explicit set of explanations (e.g. France unrest: H1 the stated cost-of-living/
   schools story; H2 a legitimacy/representation crisis; H3 …; "other/unknown"), each with a weight. The official account is one hypothesis among
   others, not the default. Unresolved space stays visible.
3. **Information = what moves the model.** An observation is worth keeping in proportion to how much it shifts hypothesis weights (its likelihood
   ratio between hypotheses), its novelty against baseline, and its source's reliability. Evidence that discriminates nothing is noise; we summarise
   and drop it. This is the compression rule.
4. **Revealed behaviour over stated positions.** Money, prices, ships, flights, jamming, satellite change, who shows up and where are harder to fake
   than statements. Divergence between what actors say and what they do is itself one of the strongest signals.
5. **Sources earn trust by track record, per topic.** Every source and actor gets a reliability and a bias estimate, learned from how its past
   claims held up, not from its status. Narrative divergence between sources is signal.
6. **Discriminating indicators.** Each hypothesis says what we'd expect to see if it were true. We watch those indicators specifically, so new
   observations land on a question.
7. **Prediction closes the loop.** Hypotheses generate forecasts (Pulses, calendar watches, market bets). Reality scores them and re-weights both
   the hypotheses and the sources that supported them. This is how the model stays honest and keeps evolving.

## Shape (what is stored)
- **Graph:** entities, relations and dated observations with provenance (the corpus index today).
- **Situations → hypotheses → indicators**, with weights and a dated weight history (why each move happened, citing the observations).
- **Source/actor reliability and stance** per topic.
- **Forecasts and their scores** (Pulses, markets, watches).
- **Compressed history:** raw items roll into "what changed" summaries once they stop moving weights.

At our scale this fits easily: millions of observations and their weights are a few GB of structured text. No neural network is needed now: the
"weights" are interpretable numbers (hypothesis probabilities, source reliabilities, edge strengths) that the system updates continuously.
Embeddings can come later for retrieval.

## How it maps onto what exists
The corpus index holds observations. Pulses become proper hypothesis sets with indicators. The prediction bots and the scored forecasts become the
reality check. The Explore feeds are judged by whether they feed discriminating indicators: attack logs, ships, satellite and jamming stay only
where they bear on a hypothesis we hold.

## First build steps (when usage allows)
1. Hypothesis sets with indicators for the active situations; observations tagged with which hypotheses they support or weaken.
2. Source reliability from resolved claims, forecasts and markets.
3. Feed audit under rule 3: keep what discriminates, compress or drop the rest (attack log, maritime, satellite, GNSS first).
