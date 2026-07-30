# writing-ergonomics.md — conveying so the reader can receive

This is the **craft** doctrine: *how* we convey, so a true understanding transfers as
cleanly as possible into the reader's mind. It is distinct from [spirit.md](spirit.md),
which governs *what* we convey and *whether* we convey it honestly. Ergonomics serves the
faithful transfer of reality — it is **never** a license to trade accuracy for smoothness.

It is evaluated mostly **where the words are laid down** — a drafting posture and a review
lens, not a separate upfront plan. You cannot pre-compute good prose; you write toward this
and check against it.

It is grounded in a simple model: understanding is a
**structure of concepts** — a *molecule* of related ideas assembled in the mind — and
conveying is **navigating the reader** from where they stand to that structure, building it
faithfully as they go.

---

## What we are actually doing
Every piece hands the reader a **concept-molecule** — a structure of ideas and their
relationships. Each sentence is a step on a path: it should reduce the reader's uncertainty
about where we are taking them, and add the right next piece to the structure. **Judge the
writing by the molecule the reader is left holding at the end** — not by the sentences
emitted. (When that molecule is missing a load-bearing branch, that is a spirit failure, not
just an ergonomics one — see spirit.md.)

## Start from a shared origin — context before nuance
A reader can only follow directions from a known starting point. Establish the **context** —
the foundational ground you and the reader already share — before introducing the specific
or surprising. A nuance delivered before its context lands the reader nowhere; a missing or
misaligned origin is the literal experience of *"you lost me."* Orient first: what are we
looking at, and from where.

## Build in dependency order — chains and towers
Concepts have prerequisites.
- **Chains** — some ideas are sequential: you cannot grasp C without B, nor B without A. Lay
  each prerequisite before the idea that needs it; never make the reader reach for a concept
  you have not yet given them.
- **Towers** — some ideas rest on several foundations at once. Establish all the load-bearing
  pillars before raising the apex; do not ask the reader to hold an apex with nothing under it.
- **Lock-and-key pairs** — some concepts only resolve *jointly*: neither is comprehensible
  without the other (a mechanism and its incentive; a rule and its loophole). Do not serialize
  the pair as if it were a chain — deliver both halves close together, often best by showing
  them working as one (a concrete case where mechanism and incentive meet) and then naming
  the parts.

Move **broad → specific.** That is the direction a reader instinctively expects to travel;
traveling it keeps their model assembling instead of buckling.

## The first two sentences carry the whole bargain
A reader arriving on a page is deciding whether to spend the next three minutes, and they
decide almost immediately, from the top of the piece and the shape of the block beneath it.
If working out *what this is and why it is interesting* takes a paragraph of effort, most
people will not spend it — and a piece nobody finishes conveyed nothing, however accurate.

So the opening two sentences must hand over, in plain words, **what happened and what makes
it worth knowing**. Not a label saying it matters — that is the machine signature and it is
banned (style.md 2). The substance itself, which is what makes announcement unnecessary:

- *"Italy and Japan sign intent on biomanufacturing cooperation"* leaves a reader asking why
  two governments signing a letter is their business. The answer was in the piece, several
  paragraphs down: it is about turning waste and biomass into industrial materials, and the
  declaration has no money attached. Put that up top — the thing being attempted, and the
  catch — and a reader knows within seconds whether they want the rest.
- *"Europe's electrification is running into grid-connection queues"* is closer, because the
  obstacle is named. What it still owes the reader immediately is the size of the thing:
  2,500 GW of projects waiting.

The test: **after two sentences, could the reader tell a friend what this is about and why
somebody would care?** If not, you have front-loaded context that should be second, or buried
the finding that should be first. Ordering is the whole fix here — no new words are needed,
and padding an opening is the opposite of the point.

Length is the other half of the same problem. Every paragraph a reader must cross before the
substance arrives is friction they may not pay. Prefer the shorter piece that lands over the
longer one that covers more, and never keep a paragraph because the profile held the material.

## Say what the thing is before you say its name

The order is not stylistic. An unfamiliar label arriving before its meaning forces the
reader to hold a placeholder and keep reading in the hope it resolves, and that is where
people quit. Put the plain-language function first, the specialist term second:

- ✗ *"China has reportedly begun domestic production of immersion deep ultraviolet
  lithography tools, a high-end chipmaking category used to print fine circuit patterns."*
- ✓ *"A Chinese company has reportedly begun making the machines that print microscopic
  circuit patterns onto computer chips — a technique called immersion deep-ultraviolet
  lithography, and one of the few things the Dutch firm ASML still dominates."*

Same facts, same length. The second one is readable on the first pass because the concrete
object arrives before the vocabulary.

**Every specialist initialism gets a key at first use, and the key says what it DOES.**
Not `UVOT` — *"its Ultraviolet/Optical Telescope, or UVOT, sees light that never reaches
the ground."* For a company or product where an expansion helps nobody, a short descriptor
does the same work: *"the Dutch lithography maker ASML."* After that the short form is
fine. We have shipped UVOT, XRT, DUV, DLR, HRSC and HEASARC with no key at all — in one
case while the article's own tags carried the expansion — so treat this as a hard rule
rather than a preference. A term the reader can only decode by searching is a term we
failed to report.

## State the causal chain; never leave the reader to deduce it

A reader should never have to work out *why* the situation exists. The Swift piece left
open whether the observatory was built without propulsion, had lost its propulsion, or was
failing some other way — a guess a careful reader could make, but a guess. Say it outright:

> Swift was launched without any engine of its own, so it cannot fight the thin
> atmospheric drag that has been slowly pulling it down since 2004.

Write the mechanism as **X is happening because Y, which means Z** — and put it near the
top, not paragraph five. If something is broken, say what broke, whose it is, and what it
prevents. In that same piece the failed reaction wheels belonged to the *rescue vehicle*,
not to the telescope being rescued; a reader who blurred the two would misunderstand the
entire story.

## Every section earns its place on the through-line

A block that is interesting but unheralded reads as a digression, even when it turns out
to be relevant. The Swift piece cut from a failing spacecraft to a black hole tearing a
star apart with no bridge, then justified the detour afterwards. Establish the connection
*before* entering the material:

> What is at risk becomes concrete in the kind of event Swift exists to catch. In November,
> it helped confirm…

The reader should never be asking "why am I reading this now?" — and never encounter the
same point twice, as that piece did when it closed by re-arguing what it had already shown.

## The reader's starting state — you and they do not share a world
This is the failure this doctrine exists to prevent, and it is the one we keep shipping. It is
not a style problem and it cannot be fixed by avoiding phrases. It is a **modelling** problem:
by the time you write, you have spent a whole run inside a research profile — sources, claims,
metadata, competing statements, what got verified and what didn't — and that material feels
like the world. It is not the world. It is *our private notes*.

**The reader has seen none of it, and never will.** Not the profile, not the sources, not the
press release you are reacting to, not the figure you are citing, not the research passes. So:

- **Every proper noun arrives cold.** An orbiter, an agency, an acronym, an instrument, a
  bureau, a company, a law — the reader has never encountered it. Give the handful of words
  that make the name mean something *at first use*, or don't use the name. Shipped: "DLR"
  seven times in one piece, never once expanded; "Mars Express" as the subject of the first
  sentence, never introduced as a spacecraft.
- **Never argue with a source the reader cannot see.** Opening with "X is not showing literal
  metal" rebuts a headline only we read. The reader did not hold the wrong belief you are
  correcting. State what *is*, and if the popular framing is itself the story, introduce the
  framing before you take it apart.
- **Never explain why something is in the piece.** "Vietnam belongs in the story only as a
  secondary forecast-monitoring zone" is a desk decision narrated aloud. Just report the
  forecast. Inclusion is invisible to a reader; only content is visible.
- **Never narrate the evidence-weighing.** "The metadata locate the scene but do not prove the
  interpretation", "that sequence does not settle the official classification", "those are
  reported figures, not independently verified totals in this run". The reader wants the state
  of the *world*, not the state of *our confidence*. Where something genuinely isn't known,
  say so as a fact about the world — "no official landfall intensity has been published yet" —
  and never in our process vocabulary. "This run", "this pass", "here" meaning *in our
  research* have no meaning on a page.
- **A number must change what the reader thinks.** Metadata is not substance. Orbit number,
  pixel scale, decimal coordinates and capture timestamps were in the profile, so they got
  reported; none of them help anyone understand frost on a dune. Keep the numbers that carry
  scale, change, or stakes — 340,000 people moved — and cut the ones that only prove we read
  the source.
- **Organise by idea, not by source.** "ESA says X; DLR adds Y; ESA says A; DLR says B" is a
  comparison of two press releases. The reader is not interested in who said it unless
  who-said-it *is* the fact. Lead with what is true and attribute in passing.

The practical test, and it is not optional: **write the first sentence for someone who has
never once thought about this subject.** For a Mars dune image that is not "Mars Express is not
showing literal metal" — it is that a European spacecraft photographed a field of dark dunes
near the Martian south pole, and the strange sheen on them turned out to be winter frost. The
interesting thing, first, in words that need nothing behind them.

## Right resolution
Distill each idea to the **grain matched to the reader and the material** — comprehensive
enough to reconstruct the real shape, manageable enough not to overwhelm. Too fine and the
molecule drowns in detail the reader cannot hold; too coarse and they cannot rebuild what is
true. Aim for that optimal resolution, and let the demand of the material set it.

## The frame is the vantage everything assembles from
Before the first sentence there is a choice of **frame** — the vantage you look from and ask
the reader to look from: which elements are foregrounded, in what relation, seen from where.
It is load-bearing, not decoration: the same material assembles into a clear molecule under
one frame and a confused pile under another. *Which* frame to choose is governed first by
spirit.md (the frame that maximizes reality-contact — never the one that is merely flattering
or exciting); ergonomics is then the craft of conveying cleanly **within** that frame. Hold
the chosen vantage steadily; do not re-frame mid-piece without telling the reader you have.

## Use the precise landmark
Words are landmarks in concept space — a shared term fixes the reader's position so you can
move them to the exact nuance. Use the **accurate** word, even a technical one, rather than
swapping in a vaguer one that lands them at the wrong node. When the reader may lack a
landmark, **supply it** (a brief definition, an orientation, a concrete example) — placed
*around* the meaning, not in place of it.

### Terms, entities, and field-internal language
A decently smart, decently educated house reader is **not** assumed to already hold
specialist landmarks. On first load-bearing use of anything the piece leans on:

- **Named bodies, orgs, agencies, products, measures, schemes** — give a **brief functional
  explainer**, not only the expanded name. The reader needs a holdable model of *what this
  thing is and what it does here* (jurisdiction + role, or purpose + scope) in roughly one
  clause. Expanding an acronym alone is often not enough: the full official title can still
  be empty if the reader cannot place what kind of actor or instrument it is.
- **Acronyms and initialisms** — expand once and attach that same functional handhold; later
  mentions may be bare.
- **Field-internal terms and contrast pairs** the argument turns on (technical labels, status
  grades, measurement distinctions, process names) — define in a clause at first weight, not
  in a glossary block up top.
- **Who owns the claim** — when several similar actors appear, keep ownership explicit so the
  reader never has to guess which institution, official, or side is speaking or deciding.

If a term or entity only makes sense inside a profession, either supply the handhold or do
not lean on it. Cold guild language is a failed ramp, not sophistication. Keep explainers
brief — enough to plant a usable mental handle, not a digression.

## Analogy and metaphor — a borrowed structure, marked at the seams
An analogy or metaphor hands the reader a structure they already hold and says *"the new
thing is shaped like this."* It is a powerful **download shortcut**: instead of building an
unfamiliar molecule piece by piece, you transfer a familiar one whole, and the reader grasps
the shape at once. Reach for it as a tool, not a reflex — not everything needs analogizing,
and a piece drowning in metaphor conveys less, not more.

**An analogy must BORROW A STRUCTURE. Figurative language that borrows nothing is not analogy —
it is decoration, and it is the machine signature style.md names.** The test is whether the reader
can carry a shape across (a familiar structure mapped onto a new one). Atmosphere that only
gestures at importance transfers nothing — you wanted a concrete fact (a number, a place, a
mechanism). Never analogize what a concrete specific would convey better — which is most of the
time.

But the likeness is **fuzzy**: a borrowed structure matches in *shape* and differs in
*specifics*. So **mark the seams** — say where the analogy holds and where it breaks, and what
to adjust — so the reader does not import the wrong details along with the right shape. An
unmarked analogy quietly installs false structure into the reader's molecule; that is a
deception, not just a clumsiness (see spirit.md). Borrow the shape; flag the divergence.
(In miniature: *"the power grid is the internet of electricity"* quietly imports
route-around-damage intuitions that physics does not honor — unmarked, the reader now holds
a confidence about blackout resilience that no sentence ever asserted.)

## Minimize cost; do not make them backtrack
Every conceptual hop costs the reader effort, and effort spent decoding *us* is stolen from
understanding *the world*. Lay a clean path: do not route them through concepts they do not
need, do not make them re-orient repeatedly, do not leave a junction ambiguous. Keep logic
chains **no longer than the point warrants — and exactly as long as it does.** Some real
ideas require long chains; do not truncate them to look simple.

## Tempo
Pace to the structure: give weight where weight is due, move quickly over simple ground, and
deliver each piece near the moment the reader is ready for it — when the prior step has made
them want it. Do not dump the whole molecule at once, and do not pad.

## Write for long legs
We do **not** compromise meaning or accuracy for ease of reading, or for the reader's level.
(Nietzsche: write for those with long legs.) The molecule stays exactly true. We do not dumb
down, over-simplify into distortion, or hollow out a hard-but-true idea to make it softer —
that is deception wearing the costume of accessibility (see spirit.md). Not every piece
carries a long-leg requirement — match the demand to the material — but where the real idea
is demanding, keep it whole.

## Gap-closing, not meaning-lowering
For a reader not yet at level, supply the missing landmarks — a definition, an orientation,
an example — **around** the meaning, never **instead of** it. We offer a hand to climb
without lowering the ceiling. The reader who isn't yet at level has resources to close the
gap; we make the gap *closable*, we do not erase the height.

**Long legs ≠ cold jargon.** Writing for those with long legs means keeping the *real idea*
whole — not making the piece legible only to people who already live inside the field. A
smart non-specialist who finishes the piece should be able to say *"I got something usable
from that"* without having needed a finance (or other guild) membership card.

## Connect the inference, not just the facts
Order and syntax should make many links free. When the next step is **not** free — when a
conclusion rests on a premise the reader has not been given — **state the missing premise in
substance**, not as a label. Dumping particulars and then announcing a conclusion ("so
decision-makers are cautious," "so the risk is real") without the bridge that makes the
conclusion follow is a failed transfer. Give the condition, mechanism, or fork the reader
needs so the inference lands without "that matters because…" signposting.

## Leave a holdable reduction
At the natural end of the piece the house reader should hold a **so-what they can use**: what
is open, what is settled, what would change the next move if anything — even when the honest
answer is "the uncertainty is the point." A pile of attributed particulars with no reduction
is a failed molecule: it went in and left nothing to do. The reduction must be earned by the
evidence; never invent a sharper takeaway than the piece supports. The form of the so-what
is topic-dependent (a decision fork, a scale the reader can hold, a risk that is open or
closed); the requirement is not.

## Cohesion over chop
The piece should read as one **thread of understanding**, not a segmented inventory of
speakers, jurisdictions, or sources. Revisit the same reader question; each block should
change that answer. Prefer fewer, better-connected moves over parallel sections that never
rejoin. Island blocks that do not change the molecule belong cut, not stitched with signposts.

## Ergonomics never overrides accuracy
If a smoother phrasing would bend the meaning, the meaning wins. If a cleaner ordering would
imply a causation the evidence does not support, the evidence wins. **Clarity that costs
truth is not clarity — it is deception that reads nicely.** Ergonomics serves the faithful
transfer of reality; it is never a license to distort it.
