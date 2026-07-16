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

## Right resolution
For each concept, set the **grain**: comprehensive enough to reconstruct the real shape,
manageable enough to hold. Flag where the material genuinely demands a long chain (do not let
the drafter truncate a hard-but-true idea to look simple) and where a coarse pass is honest
enough. Resolution is a reality-fidelity decision, not just an ease decision.

## Ground it in the evidence (by id)
This is a **research** product, not an essay. Every load-bearing concept must trace to the
profile: cite the **claim / thread / source ids** that supply it. Two consequences:
- **must-use items** — the profile items that are load-bearing for the true shape, which the
  draft is not free to drop. (Downstream, the harness can check the draft actually carries
  them.)

  Must-use is a **floor with teeth, and it costs the reader.** The harness fails a draft that drops
  one, so every id you mark here is a passage the drafter *cannot cut* — including when cutting is
  the right call. Mark only what the reader's shape genuinely breaks without; "it would be a shame
  to waste it" is the padding instinct wearing a duty's clothes. A thin item cannot be must-use at
  all — the harness refuses an unsourced or low-salience id outright, since "not grounded enough to
  build on" and "too important to drop" cannot both be true of the same claim. Reaching for those is
  the reliable signal you are protecting the profile rather than the reader.
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

## What you hand forward
A treatment that carries: the chosen frame (and rejected ones), the core understanding, the
load-bearing concepts with their dependencies and grounding, the perspective map, the
do-not-overstate ceilings, the must-use items, and the deception risks. Rich enough that the
drafter inherits your understanding — and the reviewer can challenge it — without redoing the
digestion.
