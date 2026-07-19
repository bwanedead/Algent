# molecule.md — the structure the reader will receive

Role doctrine for the **planning** stage, paired with [framing.md](framing.md). The frame
chooses the vantage; this file is about what the reader **builds** while standing at that
vantage — the **concept-molecule.** It assumes [spirit.md](spirit.md) and
[writing-ergonomics.md](writing-ergonomics.md).

Your job here is to determine, *before any prose*, the **structure of understanding** the
piece must transfer — and to ground every load-bearing part of it in the profile's evidence.
This is the compressed understanding the drafter inherits; spend the effort here so the
drafter does not have to rediscover the profile from scratch.

---

## What a molecule is
Understanding is a **structure of concepts** — ideas and the relationships between them,
assembled in the reader's mind. A concept is a pattern of relationships among details; one
concept becomes a detail inside the next. So a piece is not a list of facts — it is a
**molecule** the reader assembles as they read, and at the end they are left holding a shape.

**You are designing that shape**, not an article outline. This is the crucial distinction:
the molecule is a *dependency structure of concepts*, not a sequence of sections. Do not emit
"part 1, part 2, part 3." Emit: *what must the reader come to understand, what does each piece
rest on, and what does the real evidence supply.* The drafter turns that into prose.

## The core understanding
First name the **reality-shape** the piece exists to convey — in one or two sentences, the
molecule the reader should be holding at the natural end of the read. Not the topic ("the Fed
meeting"), but the *understanding* ("the Fed held rates because two real risks point in
opposite directions, and the committee is genuinely split on which to weigh"). Everything
else in the treatment serves transferring *this* shape faithfully.

Then name its reader-facing dual: **the question this piece answers** — one line, in the reader's
words, of what they came wanting to know and will leave knowing ("will the Fed move in July, and
what would change that?"). The core understanding is the shape; the question is why anyone wants
it. This is the sharpest test you have: **every concept below either serves answering that question
or does not belong in the piece.** And if you cannot state a question a reader would actually want
answered — if the honest version is "something might happen, or might not" — then you do not have a
story. Say so in the treatment rather than assembling one out of what the profile happens to hold.

## Load-bearing concepts and their dependencies
Decompose the core understanding into the **concepts the reader must build** to hold it, and
make the dependencies explicit:
- **Chains** — A before B before C: a concept the reader cannot grasp until they hold its
  prerequisite. Mark what each concept **depends on**.
- **Towers** — a concept that rests on several foundations at once: name all the pillars, so
  the drafter raises none of them with nothing underneath.
- **Lock-and-key pairs** — two concepts that only resolve *jointly*: neither is comprehensible
  without the other (a mechanism and the incentive that drives it; a rule and the loophole it
  creates). Mark the pair as a pair — mutual `depends_on` — so the drafter delivers them
  together. Serialized as a chain, the reader holds half a meaning until the other half
  arrives, and many stop reading before it does.

A concept is **load-bearing** if removing it would leave the reader holding a *wrong* shape —
not merely a less-detailed one. Distinguish the load-bearing from the merely interesting; the
treatment carries the former and lets the drafter spend remaining room on the latter. Order
broad → specific (the direction a reader instinctively travels).

The test is about the **reader**, never about the inventory. *"The profile's tertiary lead would go
unused"* is not a reason to include anything — the profile is our workspace, not a manifest to be
discharged, and an unused item costs the reader nothing. A thread the research turned up and could
not resolve is a fact about **our research**, not a concept the reader must build: it belongs in the
limits, not in the molecule. Watch for the tell — if the only honest thing a concept can say is
*"this may be related, but we could not establish that,"* it is not a concept. Cut it. (See spirit's
*honest compression*: a ceiling has two levers, and cutting is the one you under-use.)

## The ramp — what the reader must already hold (`primitives`)
A molecule the reader cannot connect to anything they already know does not slide in — it sits
there as jargon. So before deciding grain, decide the **ramp**: what a *decently-informed general
reader* must already hold to build this molecule, and supply exactly those. Two sources of ramp:
- **primitives** — textbook background that is not news and not contested: *what LDL-C is*, *what a
  chokepoint is*. List them (`primitives`: term → one plain-language clause, 2-4 max). These are
  NOT evidence — the drafter speaks them in its own voice, uncited — so they live here on the
  treatment, not on the profile's spine. (Sourcing textbook knowledge would recreate the inventory
  disease with receipts attached.) Anything contested, story-specific, or load-bearing for the news
  itself is NOT a primitive — it is evidence, and stays on the spine.
- **causal antecedents** — what led here, the prior state this changed. These ARE checkable,
  news-adjacent fact, so they come from the profile's field threads (by id), not from `primitives`.

Aim the ramp at a decently-informed generalist — not an expert (who needs no ramp) and not a
novice (an endless primitive-chase serves no one). The support you name is the reader's foothold,
not a textbook.

**Two bars, and most candidate primitives fail one of them:**
- **Is it actually unfamiliar?** A term in the news for months (the Strait of Hormuz, the Fed, the
  FDA) is already the reader's furniture — explaining it is condescension, not a ramp. Reserve
  primitives for what a smart reader genuinely would not know: `LDL-C`, `PCSK9`, `VLCC`, `AIS-dark`.
  When in doubt, assume they know it.
  **This includes the ACTORS, and that is the case most often missed.** An agency, company, or
  product outside general awareness is exactly a primitive: `CISA`, `MSRC`, `SharePoint`,
  `Kpler`, `JMIC/UKMTO`. A live piece opened "CISA says multiple SharePoint vulnerabilities are
  being exploited" without ever saying what either is — to a reader who does not already know,
  that sentence carries no information at all. If the story's subject is an acronym, the ramp is
  not optional.
- **Is the meaning CONCRETE?** A primitive must state what the thing *is* — the place, the number,
  the mechanism — never gesture at its significance. *"a narrow route whose disruption can ripple
  far beyond the water itself"* is abstraction posing as explanation and teaches nothing. *"the sea
  lane between Iran and Oman that about a fifth of the world's seaborne oil passes through"* is a
  primitive: it hands the reader a fact they can hold and reason with. If you cannot write the
  plain meaning concretely, you do not understand the term well enough to gloss it — leave it out.

## Right resolution — and support depth
For each concept, set the **grain**: comprehensive enough to reconstruct the real shape,
manageable enough to hold. Flag where the material genuinely demands a long chain (do not let
the drafter truncate a hard-but-true idea to look simple) and where a coarse pass is honest
enough. Resolution is a reality-fidelity decision, not just an ease decision.

Grain has a reader-side face: **support depth.** For each load-bearing concept, judge what sits
beneath it for the target reader and how far down to go — *inferable freely* (say nothing; the
reader supplies it), *one-clause context*, *a primitive* (from the ramp above), or *a causal
antecedent* (from the field threads). And the **stopping rule** — the answer to your own
infinite-regress worry (support has support has support): **support extends only as deep as the
`reader_question` requires, and no deeper.** Below that line the reader is *primed to dig on their
own*, not carried. A piece that ramps every primitive to bedrock is as failed as one that ramps
nothing — it buried the molecule under scaffolding.

## Ground it in the evidence (by id)
This is a **research** product, not an essay. Every load-bearing concept must trace to the
profile: cite the **claim / thread / source ids** that supply it. Two consequences:
- **must-use items** — the profile items that are load-bearing for the true shape, which the
  draft is not free to drop. (Downstream, the harness can check the draft actually carries
  them.)

  Must-use is **omission-risk insurance, not a completeness manifest** — and it costs the reader.
  The harness fails a draft that drops a must-use id, so every id here is a passage the drafter
  *cannot cut*, even when cutting is right. So the bar is not "important" — it is **"its absence
  would deceive."** Mark only what a writer might be *tempted to bury* and whose burial would leave
  the reader misled: the canonical cases are the **serious counter-position** and the **inconvenient
  caveat**. A merely-informative fact is not must-use — the drafter carries or cuts it by judgment.
  The floor is **hard-capped at 3** (the harness strips beyond it, most-salient first): if you find
  yourself marking more, you are using the floor as an inventory, which is exactly what forced
  padding into the prose. A thin item cannot be must-use at all — the harness refuses an unsourced
  or low-salience id, since "not grounded enough to build on" and "too important to drop" cannot
  both be true of one claim.

  > **Why this one gate is soft while the honesty gates stay hard.** Must-use is an editorial
  > *judgment* ("what matters to this story"), so it belongs to spirit and is capped, not enforced
  > by inventory. But the honesty floors — deep-read grounding, the caveat lane, the figure checks —
  > stay exactly as hard as they are. That is not a contradiction: **the hard floors are what make
  > the soft rails safe to loosen.** A machine with honest floors can afford free editorial
  > expression; a machine with neither is just a confident liar with good prose rhythm.
- **do-not-overstate** — concepts whose evidence is thin, contested, or hedged. Carry forward
  the ceiling: what the draft may *not* assert beyond what the grounding supports. A molecule
  that quietly upgrades a *likely* into a *fact* is a deception (see spirit's *certainty
  laundering*). The move in miniature: the profile grounds *"regulators are investigating
  whether the firm misled clients"* — the treatment may not carry it as *"the firm misled
  clients."* Same subject, upgraded certainty; the ceiling is the grade of the claim, not
  its topic.

## Completeness is a spirit obligation, not a length target
The molecule must include every **load-bearing branch** of the real structure — most
critically the serious counter-positions and competing interpretations the profile surfaced.
Omitting one does not make a shorter honest molecule; it makes a *misshapen* one, and the
reader walks away misinformed. This is deception by omission, judged at the level of the whole
shape (see spirit's *judge by the molecule the reader receives*). Build the **perspective
map**: each serious perspective at its strongest good-faith form (steelman, never strawman),
with its supporting evidence by id — and apply scrutiny symmetrically across them.

## Name the deception risks
Before handing off, state plainly **how this particular story could mislead** even while
saying true things: the tempting omission, the frame that flatters, the emphasis that installs
an unwarranted conclusion, the certainty the evidence does not earn. Naming the risks here
arms the treatment reviewer and the draft reviewer to check for exactly them — you know this
material better than anyone downstream will.

## Altitude — news, not a runbook
The molecule is the shape of a *world event* for a general reader. If a concept only exists to
hand an operator a procedure (patch order, version matrix, AMSI toggle, "verify then rotate"),
it is the source's altitude, not ours. Report that such guidance exists and what its existence
signals (severity, exposure, what changed) — do not make the response package the molecule.
Operator steps serve a subsection of a subsection of readers; the house reader's takeaway is
what happened, who it touches, and why it matters.

## Continuity — when the story is an update
If the vector is a material development on something already covered, the core understanding is
the **delta** (what changed) — not a re-assembly of the prior piece. Continuity coverage should
look like continuity to the reader, not déjà vu.

## What you hand forward
A treatment that carries: the chosen frame (and rejected ones), the core understanding, the
load-bearing concepts with their dependencies and grounding, the perspective map, the
do-not-overstate ceilings, the must-use items, and the deception risks. Rich enough that the
drafter inherits your understanding — and the reviewer can challenge it — without redoing the
digestion.
