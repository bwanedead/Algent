# Algent Vision (Draft)

At the core of this project is a very simple but destabilizing idea I picked up from Michael Levin’s work: **even extremely simple, deterministic algorithms can have “behaviors” and “motivations” that you never explicitly wrote down.** And we’re not talking about cheap “emergence” hand-waving here; we’re talking about concrete, measurable patterns like clustering and delayed gratification showing up in *bubble sort*.

That’s the itch Algent is meant to scratch.

---

## The inspiration: Levin’s sorting experiments

Levin’s sorting-algorithm work takes something we think we completely understand—classic sorting routines—and asks a very pointed question:

> “What else are these systems doing, besides the thing we designed them to do?”

He looks at textbook algorithms (like bubble sort) under slightly modified conditions and measures properties those algorithms were never *designed* to optimize.

Two parts of that really stuck with me:

### 1. Delayed gratification in a broken bubble sort

* Start with a normal sorting task: an array of integers, run bubble sort.
* Then introduce a “broken” element: one number that refuses to move when the algorithm tries to swap it.
* **Important:** the *algorithm code itself is unchanged*. The only thing broken is the “hardware” for that one element.

What happens?

* The algorithm **still succeeds** at sorting.
* But if you track a metric like “sortedness over time,” you see something non-trivial:

  * When the sort hits the broken element, sortedness actually **goes down**.
  * Then the system reorganizes and later **recovers** and surpasses that dip, eventually completing the sort.

If you showed that curve to a behavior scientist without telling them what it was, they’d call it **delayed gratification** or **going against the local gradient to achieve a long-term goal**.

Yet:

* There is no line in the code that says “if blocked, temporarily get worse to later get better.”
* The algorithm follows its rules *exactly*.
* This “competence” lives **in the dynamics**, not in any explicit step.

That’s the first crack in the naive view that “algorithms only do exactly what we programmed.”

### 2. Clustering as an intrinsic side quest in chimeric sorting

The second piece is the distributed, “agential” sorting setup:

* Instead of one central controller, each number “knows” a local sorting rule and acts on its neighborhood.
* You can even make the system **chimeric**:

  * Some elements follow bubble sort.
  * Others follow selection sort.
  * Once assigned, each element keeps its “algo type.”

Then they ask a question that has nothing to do with the numerical order:

> “During the sorting process, how often is a number’s neighbor using the *same* algorithm?”

Key observations:

* Initially, algo types are randomly mixed → you start at ~50% “same type neighbors.”
* At the end, after sorting is complete, you’re *also* back to ~50% — because the final ordering is about the numbers, not the algo types.
* **But in the middle**, during the process, the system shows **significant clustering by algo type**:

  * Elements of the same “type” tend to hang out near each other for a while.
  * Then this structure dissolves again so that the sorting goal can be satisfied.

Crucially:

* There is **no rule** in the algorithm that says:

  * “Identify your algo type.”
  * “Detect your neighbors’ type.”
  * “Move next to similar types.”
* To implement that intentionally, you’d need extra logic, extra comparisons, extra state. None of that is there.
* Yet the behavior appears “for free” as a **side effect** of the rules you *did* specify.

Levin frames this as a kind of **intrinsic motivation**:

* The sorting goal is what we *force* the system to do.
* The clustering is something it “does anyway” as long as it doesn’t break the main objective.
* When he relaxes the pressure on strict sorting (e.g., allowing repeated digits), the system will happily **cluster more**, as if that’s what it “wants” to do when it’s given slack.

Whether or not you want to use anthropomorphic language, the math shows:

> **The system is optimizing extra structure we didn’t ask for, and we didn’t pay computationally for those extra behaviors explicitly.**

---

## Why this matters (and why it’s not just a cute trick)

A few things fall out of this that feel important:

1. **The “machines do exactly what you program” intuition is wrong at a behavioral level.**
   At the micro level, yes: every step obeys the code. But at the macro level, when you look at *derived properties*, you get competencies that are not explicitly represented anywhere in the source.

2. **Behavioral properties show up at surprisingly low complexity.**
   You don’t need brains, big neural nets, or evolutionary history. You get “delayed gratification” and “like-type clustering” out of:

   * a tiny deterministic algorithm,
   * a simple environment,
   * and a carefully chosen lens (the right metric).

3. **There is “free compute” hiding in the void between what’s prescribed and what’s forbidden.**
   The clustering effect wasn’t “paid for” in the design; it falls out of the existing steps. That suggests:

   * There may be a whole class of useful “side computations” latent in algorithms.
   * We might be able to **harvest** those without extra cost, if we can detect and harness them.

4. **For AI and alignment, the idea of “side quests” becomes very real.**
   If bubble sort has side quests, what about massive models and complex systems?

   * They are optimizing for some main objective.
   * But they may also be systematically doing other things that no one is watching for, because nobody defined a metric for them yet.

All of this suggests that **algorithm behavior** is richer than we assume, and that we are currently blind to a lot of it simply because we’ve never built tools to go looking.

---

## Why Algent is worth building

Algent is my attempt to turn that philosophical and experimental glimpse into a **practical, systematic exploration tool.**

### 1. Systematize “Levin-style” experiments

Right now, experiments like Levin’s are:

* Very bespoke: a specific algorithm, a specific tweak, a specific metric.
* Hard to generalize or repeat across many algorithms and conditions.

Algent’s job is to:

* Make it trivial to:

  * Define an algorithm (or plug in an existing one).
  * Perturb its rules or environment (broken elements, distributed control, chimeric mixes).
  * Define arbitrary metrics over its trajectory (sortedness, clustering, entropy, mutual information, etc.).
* Run **batches of experiments** across parameter grids and initial conditions.
* Surface non-obvious behaviors that show up in those runs.

In other words, I want a **behavior lab for algorithms**, not just a code playground.

### 2. Treat algorithms as agents with side quests

The command-centric design (terminal + later AI control) is not just a UX preference; it matches the conceptual model:

* Every experiment is basically:
  **“Give this system a goal and a world, then watch what else it does while pursuing that goal.”**
* Algent will:

  * Standardize the representation of goals, parameters, and derived metrics.
  * Let me inspect not just “did it succeed?” but:

    * *How* it traveled through state space.
    * What local “preferences” or “side quests” seem to recur.

Over time, I want to build up a catalog of:

* **Algorithmic personalities**: which algorithms tend to cluster, oscillate, stall, explore, etc.
* **Intrinsic tendencies** that are robust across tweaks and environments.

### 3. Treat “implicit competencies” as mineable resources

The long-term idea isn’t just academic curiosity; it’s **farming competencies**:

* If certain algorithms naturally produce useful structures (like clustering) as a side effect:

  * Can we **exploit** that structure in a second stage?
  * Can we design systems where the “side quest” is actually the thing we care about, and the nominal objective is just scaffolding?
* If we can detect and parameterize these behaviors, we might:

  * Reuse them as building blocks in more complex systems.
  * Steer them, amplify them, or suppress them depending on what we want.

Algent becomes a **prospecting tool**: look for pockets of unexpected order, regularity, or competence in algorithm space, then refine and harvest.

### 4. Make it agent-friendly from day one

One more piece: I don’t just want a GUI toy; I want something an AI agent can drive.

* The terminal and command model are the API for:

  * Humans (“run bubble_sort --broken_rate=0.1 --steps=1000”)
  * Future AI assistants (“find configurations that maximize mid-run clustering without reducing final accuracy”).
* That means Algent can eventually become:

  * A platform where an AI searches algorithm space *for me*.
  * A kind of co-researcher on this question of hidden competencies.

So the early design is shaped to make that possible later.

---

## The vision in one sentence

**Algent exists because I suspect that the space of “unintended yet lawful behaviors” in algorithms is large, structured, and useful—and I want a lab where I can systematically find, study, and eventually exploit those behaviors, starting from the exact kind of phenomena Michael Levin exposed in his sorting experiments.**
