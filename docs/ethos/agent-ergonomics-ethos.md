# Agent Ergonomics Ethos

The seam between the agent and the engine should fit the agent's natural action
grammar as closely as possible — so long as that grammar is sane, deterministic,
and structurally supportable.

This is not an argument for a fuzzy, permissive, or vague engine. It is an
argument for designing the action seam to match how the agent naturally and
repeatedly tries to express correct intent — and for **discovering** that fit
empirically by watching real runs, not guessing it once and freezing the seam.

> **Agent owns intent. Runtime owns realization.** The engine should become
> easier for the agent to drive, not looser about what actually happens.

---

## How this applies to Algent's seam (native tool-calling)

Algent's current action seam is **provider-native tool-calling** via
`create_react_agent`: the model emits standard `tool_calls` (a tool name plus
JSON args matching that tool's schema), the runtime executes them, and the loop
continues until the model stops calling tools. The final result is shaped by a
structured-output contract (e.g. `DiscoveryResult`).

So we do **not** own the per-turn envelope — the provider does — and we cannot
"evolve the accepted action contract" the way an engine with a custom action
grammar can. But the ergonomics principle applies fully to the surfaces we *do*
own, which is where the agent's friction actually lives:

- **tool names** — does the name say what the tool is for?
- **tool descriptions** — does the model reliably pick the right tool, with the
  right args, from the description alone?
- **argument schemas** (from Python type hints) — do they match how the model
  wants to express the call, or force an awkward shape?
- **result and error feedback** — when a call lands or fails, does what we hand
  back teach the model to do better next turn?
- **the structured-output contract** — is the requested output shape natural for
  the model to produce?

And the discipline below — *observe emitted forms, then pave the path the agent
actually walks* — maps directly onto **watching LangSmith / `events.jsonl` for
how the model really calls our tools, and fixing the seam where it fumbles.**
(The first such fix already happened: the model invented dead RSS URLs, so we
added a `news_feeds` catalog tool — an ergonomic repair, not a reasoning fix.)

If Algent later grows a native runtime with its own action contract, the full
"evolve the envelope toward the agent's natural form" applies to that contract
too. Until then, the levers are names, descriptions, schemas, feedback, output.

---

## 1. Core principle

When the agent repeatedly expresses the same action in a consistent, intelligible
shape, that is strong design signal. If the shape is semantically clear,
deterministic to parse, conflict-free, easy to validate, and compatible with the
execution rails, the seam should evolve toward that shape rather than forcing the
agent through an awkward notation forever.

- The agent should not need to "speak with an accent" just to use the engine.
- The engine should accept action forms natural to the agent, provided they stay
  mechanically reliable.

### 1.1 Contract discovery, not contract guessing

The deeper principle is not "make the seam match the agent's tendencies" but:
observe how the agent expresses intent in practice, identify recurring sane
shapes, and let the seam evolve toward them where safe. That means: instrument
the seam, record emitted shapes, compare repeated near-miss and valid forms,
detect stable natural grammars, then deliberately adapt — rather than freezing
the seam around a contract invented before observing enough evidence.

---

## 2. The sidewalk-on-the-dirt-path rule

Sometimes a system is designed one way on paper, but the user repeatedly chooses
a nearby, more natural path. That is often design feedback, not user error. For
agents: the engine defines one shape, the agent repeatedly emits a nearby more
natural one, the runtime rejects it, and the loop pays avoidable friction.

When this recurs, the question is not "how do we force the model to obey?" but
"is the model revealing a better seam?" If yes, pave it. This does **not** mean
accepting malformed payloads, guessing meaning, or allowing ambiguous shorthand.
It means: identify recurring sane patterns, bless them deliberately, normalize
internally, and reject only what stays ambiguous or unsafe — which requires
enough traceability at the seam to actually see what the agent emitted.

---

## 3. Why it matters

- **Reduces artificial loop friction.** Many loop failures are not reasoning
  failures but seam failures: the agent knew what it wanted but expressed it in a
  shape the engine made awkward. That wastes turns, budget, and operator time.
- **Keeps the agent truly agentic.** An overly awkward seam forces the runtime to
  script around the agent's formatting failures, quietly reclaiming authorship —
  back toward scripted flows and hidden shims. A good fit preserves "agent
  chooses intent, runtime executes with rails."
- **Improves structural honesty.** If the runtime constantly translates obvious
  near-miss intent into the "real" shape, the public contract and the true
  ergonomic contract have diverged. Correct that, don't hide it.
- **Makes evolution evidence-based.** As models and prompts change, the natural
  grammar shifts; the seam should stay observable, evidence-led, and evolvable.

---

## 4. The diagnostic split

When reviewing a repeated agent failure, ask:

- **A — Did the agent choose the wrong action?** Then improve reasoning context,
  evidence visibility, or move guidance (a *reasoning* problem).
- **B — Did the agent choose the right action but express it in a shape the
  engine made awkward?** Then the seam may need to move toward the agent (an
  *ergonomics* problem).

This is the core diagnostic. For Algent's native seam, "B" usually shows up as:
the model called the right tool with slightly-off args, or couldn't tell which
tool to use, or produced output that just missed the schema — all fixable by
better names/descriptions/schemas/feedback, not by scolding the model.

---

## 5. When to adapt the seam

Adapt only when all hold: the behavior is **recurring** (not a one-off); the
intent is **unambiguous**; the shape **maps cleanly to safe execution**; the
shape **does not collapse important distinctions**; and the pattern is **grounded
in recorded emitted behavior**. If you have not observed it in real runs, be
slow to elevate it into the accepted seam.

## 6. When not to adapt

Do not adapt to every natural-seeming behavior. Keep it invalid when the behavior
is inconsistent, the shape is ambiguous, intent conflicts across fields, the
shorthand forces runtime guesswork, meaning depends on unrecoverable hidden
state, or the pattern weakens safety rails.

> The goal is not "be forgiving." The goal is: **glove-fitting where the agent is
> repeatedly sane, strict where the meaning is uncertain.**

---

## 7. Preferred pattern

1. Observe raw emitted forms in live runs (traces, `events.jsonl`).
2. Confirm the pattern is recurring and coherent.
3. Decide whether it becomes the accepted form or a supported alias.
4. Normalize internally into one execution shape if useful.
5. Keep validation strict after normalization.
6. Add regression tests using real emitted payloads.

For Algent, "step 1" is reading how the model called the tools and what it
struggled with; the "shape" we adapt is the tool surface (name/description/
schema/feedback) or the output contract, not a hand-rolled envelope.

---

## 8. Rails still matter

Ergonomics is not anti-rail. The runtime still owns deterministic validation,
bounds checks, artifact persistence, budgets, and terminal policy. Adapt the
**shape of accepted intent**, not the responsibility for safe realization:
observe many emitted forms, accept a bounded sane subset, normalize internally,
keep execution strict after normalization.

---

## 9. Summary

- Treat recurring sane agent action shapes as design signal.
- Discover those shapes empirically from recorded runs, not assumption.
- Adapt the seam toward them when safe; allow bounded aliases for a small
  recurring family of forms.
- Keep one deterministic execution model underneath, with strict rails.

**Do not make the agent contort itself to fit a seam the engine could learn to
fit instead. Where the agent consistently walks a sensible path, pave it — and
before paving it, make sure you actually watched where it walked.**
