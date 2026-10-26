# The world model: what the brain keeps and how it learns (vision v2, 2026-10-26)

Operator's framing, refined in discussion (see also the essay "On Delineation", 2026-10-26). Ohmega is not a better intelligence database.
It is a continually evolving, evidence-grounded **model of the world**. It compresses observations into actors, conditions, relationships and
mechanisms; it keeps uncertainty where truth is unknown; it predicts; and it seeks observations that could improve or overturn its understanding.
It is judged by the predictive, explanatory and transferable value of that model, never by how much it collects.

> Don't optimise for how much the brain remembers. Optimise for how much of the world it can reconstruct, explain and anticipate from what it
> remembers.

> **Governing principle: preserve evidence, version interpretation, isolate experimentation, judge methods by their consequences.**

## 1. What the brain must be able to do
- **Delineate.** Find the fork between possible worlds, sharpen it, and search for the detail that fits one and not the other. Record exactly
  what each observation established: *hard* (a possibility contradicted, given stated assumptions), *soft* (relative weights moved), or
  *restructure* (no listed explanation fits, so add a mechanism, actor or variable). "Store only what the evidence earned."
- **Hold a worldview landscape.** Compressed regularities about how things behave (institutions, incentives, coalitions, deception, markets, physical
  systems). They tilt a question before the reasons are articulated, and they flag configurations that "move like fake water". Intuition
  proposes and flags; it is not counted as independent evidence unless it has been calibrated on held-out history.
- **Model minds and networks.** Actors have goals, beliefs (possibly wrong), capabilities, constraints and internal factions. The effective
  unit of agency is sometimes an undeclared coalition, patronage network or institution.
- **Reason about hidden structure without being institution-brained or tinfoil.** Official statements are claims with incentives. The key tool is
  the **integrity counterfactual**: how would an actor bound by its stated duties behave here? Divergence from that path, especially costly
  divergence that benefits the same parties repeatedly, reveals hidden objectives and affiliations. This holds even when the behaviour is
  statistically *normal* (if collusion is the norm, anomaly detection sees nothing). The system keeps separate assessments for: shared interest,
  ideological alignment, open coordination, tacit coordination, covert coordination and improper collusion. Inferred links are allowed in the
  graph, labelled as inferred, tied to evidence and exposed to alternatives. It also remembers when suspicion turned out mundane.
- **Track explanatory debt.** A persistent pattern the model can't explain is a first-class object that accumulates observations and candidate
  mechanisms until it resolves (mundane, covert, or new mechanism) or stays open.
- **Explore as well as exploit.** Refine known models, *and* notice what none of them anticipated. Some research is reserved for the unfamiliar.
- **Know what it can't see.** Coverage is recorded: absence of a signal means something only where the signal would have been observable.

## 2. Memory layers (logical, not separate databases)
1. **Evidence:** original records, extracted observations, attributed claims and computed features, each with provenance (producer, method
   version, sources) and **three timestamps**: when it happened, when it became available, and when we acquired it. Copies of one report are one
   evidence chain, not ten.
2. **World state:** actors, capabilities, relationships, dependencies and conditions over time.
3. **Mechanisms:** how things influence each other (economic, political, military, institutional, psychological).
4. **Beliefs and uncertainty:** possibility sets, the delineation ledger, explanatory debt and unknowns, with a dated history of every revision
   and the evidence behind it, so any past state can be reconstructed without hindsight.
5. **Predictions:** immutable dated forecasts, outcomes, scores and model versions.

Compression is reversible where possible. History and the record of *normal* behaviour are kept (baselines need them). The largest compression
is conceptual: one good mechanism explains hundreds of events. Shared evidence is compressed conservatively, because a better future model may
need what today's models ignore.

## 3. Experimental architecture: competing brains, one evidence base
Our own theories of how the brain should think may be wrong, so no single sense-making method is privileged.
- **Shared evidence substrate:** observations and claims with provenance and time semantics. No protocol's conclusions overwrite it. Interpretive
  steps that live in it (entity resolution, deduplication, extraction) are versioned and reversible, and protocols may disagree with them.
- **Protocols, i.e. bots, as versioned manifests:** attention, extraction, memory, interpretation, hypothesis, evidence, investigation, prediction
  and learning policies, plus model, prompts, tools and data access. Every meaningful change produces a new version.
- **Isolated derived memory per protocol:** each has its own hypotheses, actor graph, worldview elements, summaries and research results, in
  separate logical namespaces on shared physical storage. Nothing is promoted across branches unless an experiment says so. Branches can be
  snapshotted and forked (A → A1/A2) and rolled back.
- **Evaluation:** one experiment runner that gives protocols matched questions with strict information cutoffs (no leakage through
  summaries), records forecasts, costs and traces, and scores them. Calibration and Brier/log scores are kept separate from trading P&L and from
  market-selection skill; abstentions are evaluated too. Run component ablations as well as full-stack comparisons. The headline test: *does
  access to the world model beat the same LLM given only recent news?* If not, the architecture hasn't earned its complexity.
- **Adversarial evaluation for hidden-coordination reasoning:** use confirmed historical schemes, ordinary shared-interest behaviour and
  genuinely ambiguous cases; measure detection, false positives, calibration, and sensitivity to framing ("suspicious" or "official" labels).

## 4. Order of work
1. Inventory what exists (corpus index, Pulses, bots, traces, ledgers, registry) and map it onto the layers above.
2. **Experimental foundation:**
   - an evidence substrate with provenance and the three timestamps;
   - protocol manifests with isolated derived namespaces;
   - the matched-question experiment runner, with today's bots as Protocol A, the control.
3. Protocol B: delineation (possibility sets, the ledger, discriminating research).
4. Protocol C: strategic worldview (actor goals, integrity counterfactuals, revealed interests, inferred affiliations, coalition incentives),
   modelled deeply on two cases first: the Brazil 2026 runoff (contested institutions, affiliations) and Hormuz (strategic actors, physical
   signals).
5. Protocol D: B + C. Then the worldview mismatch detector, explanatory debt, and expected-value-of-information research.
6. Memory and retention policy set by measured value (ablations), not by guesses. Neural or learned components come only where they
   measurably beat explicit structure.

Each stage advances when its evaluation shows it works, not on a calendar.
