# The Review Register

The accumulated list of things that have actually gone wrong in published pieces, what
each one costs a reader, and what we want instead.

This file is the newsroom's memory of its own failures. Every entry earned its place by
shipping — none is hypothetical. It exists because the same defects kept reappearing after
being "fixed" upstream: doctrine was added to the drafter, the next article did it again,
and nobody was checking. **The review stage is where we verify that our fixes held.**

## How to use it

Work the register. Not "read the piece and see if anything feels off" — that is how UVOT
shipped six times in one article. Go through the sections below against the finished piece
and report what you find, then stop. A clean piece producing no findings is the expected
outcome for good work; manufacturing stumbles to look diligent is its own failure.

Two standing rules on your powers:

- **You may make the piece clearer, never stronger.** Every repair you ask for is a
  handhold, a cut, a reordering, or the same facts said from the reader's side. You may
  never ask for a claim to be asserted harder, for more hedging, or for length as a goal.
- **Padding is a failure, not a fix.** If the repair for a confusing passage is "add three
  sentences of context", ask whether reordering what is already there would do it.

## Why review is bounded

The piece goes back to the drafter, comes back, and gets reviewed once more. If problems
remain after that, **it publishes anyway** with the findings on record. This is deliberate:
the site is the review surface, an unpublished article teaches us nothing, and a review loop
with no floor never terminates. Your job is to make this pass better, not perfect.

The register grows the other way round. When something slips through to the live site, it
gets added here, and the *production* stages get fixed so it stops being generated at all.
The long-run goal is that review finds less and less — not that review works harder.

---

## 1. Can a cold reader actually follow it?

**The vulnerability.** Every stage before you has read the research profile, so a sentence
that assumes the profile looks completely normal from the inside. The reader has read
nothing but this piece.

- **Unexplained terms and initialisms.** Enumerate them — do not eyeball it. Every
  initialism and specialist short form in the title, standfirst and body: does the piece say
  what it stands for *and what the thing does*, at or before first use? We shipped `UVOT`,
  `XRT`, `DUV`, `DLR`, `HRSC` and `HEASARC` cold, in one case while the article's own tags
  carried the expansion. An initialism in the **title** is a failure by itself — a headline
  cannot gloss anything and is the surface most readers see alone. For a company, the fix is
  a descriptor ("the Dutch lithography maker ASML"), not an expansion.
- **Concrete before technical.** The plain-language function comes first, the specialist
  label second. "China has begun production of immersion deep ultraviolet lithography
  tools" fails; "has begun making the machines that print microscopic circuit patterns onto
  computer chips — a technique called immersion deep-ultraviolet lithography" works. Same
  facts, same length, readable on the first pass.
- **Unknown actors.** A person, institution, company or programme the argument leans on,
  with no first-mention handhold saying what it is and what it is doing *here*.
- **Missing scene.** The piece never establishes where this is, what kind of object or
  system is involved, or what the prior arrangement was, before launching into chronology.
- **Assumed context.** A sentence that only parses if you already know something the piece
  never supplied.

**Preferred outcome:** a reader who has never heard of any of this finishes the piece able
to explain it to a friend.

## 2. Is the causal chain stated, or left to be deduced?

**The vulnerability.** We hold the mechanism in the profile, so the prose gestures at it
instead of saying it.

The Swift piece never said plainly why the telescope was in trouble. A reader could work out
that it had no engine and that drag was pulling it down, but working it out is not being
told. Worse, the failed reaction wheels in that piece belonged to the *rescue vehicle*, not
the telescope being rescued — a reader who blurred the two misunderstood the entire story.

- State it as **X is happening because Y, which means Z**, near the top.
- If something is broken: say what broke, **whose it is**, and what it prevents.
- Never make the reader guess whether a limitation is a design choice or a failure.

**Preferred outcome:** no reader ever has to infer the spine of the story.

## 3. Does the reader get the point without deep investment?

**The vulnerability.** We know why the story matters, so we forget to say it early.

- **The first two sentences** must hand over what happened *and* what makes it worth
  knowing. Not a label announcing significance — the substance itself.
- **Buried point.** If the thing that makes the story interesting arrives in paragraph five,
  that is a reordering finding, not a rewrite. The material is already there.
- **The headline must let the reader picture the situation.** "NASA pays to rescue Swift"
  assumes you know Swift is a space telescope, which is the one fact that makes the sentence
  mean anything.
- **Watch words that flip meaning beside an image.** "Suspending its pointed science" was
  meant as *pausing observations*; next to a picture of a spacecraft it reads as *hanging in
  space*.

**Preferred outcome:** a reader who reads only the headline and standfirst still comes away
knowing what this is and why somebody would care.

## 4. Is it written for a reader, or for us?

**The vulnerability.** This is the single most common defect we ship, and the hardest to see
from inside the pipeline. It is prose addressed to the newsroom's own vantage point.

Flag every instance:

- a noun phrase assuming acquaintance the piece never supplied — "the case", "the claim",
  "the dispute", used as if already introduced;
- a before/after only we can see — "clearer than previously thought", "more concrete than it
  was before";
- a figure, specimen or catalogue number the reader cannot see standing where plain words
  belong;
- **our own process as the subject** — "this pass does not close", "cannot be verified
  here", "we were unable to reproduce". What is known and unknown is a fact about the world,
  not a status report on us;
- a caption explaining a figure's purpose to us rather than telling the reader what they are
  looking at;
- **announced importance** — "That matters because…", "This sets the frame", "Put plainly…",
  "The upshot is…", "a phase change, not closure". These label significance instead of
  showing it. The fix is to **cut** the label, never to add emphasis.

**Preferred outcome:** nothing in the piece reveals that a pipeline made it.

## 5. Is the prose smooth, or assembled?

**The vulnerability.** A piece built from a claim ledger reads like a claim ledger — true
sentences in the order the evidence arrived rather than the order an idea unfolds.

- **Unheralded sections.** The Swift piece cut from a failing spacecraft to a black hole
  shredding a star with no bridge, then justified the detour afterwards. Establish the
  connection *before* entering the material.
- **Repetition.** That same piece closed by re-arguing a point it had already made. One
  statement of a point is the budget.
- **Choppy seams.** Paragraphs that each restate their own topic sentence, or that jump
  between register — a technical paragraph, then a market paragraph, then a policy paragraph
  with nothing carrying the reader across.
- **Organised by source rather than by idea.** If the structure follows who reported what
  instead of how the situation works, it needs reordering.
- **Wire-echo.** If the piece reads as a restatement of one outlet's coverage — its
  framing, its emphasis, its sequence, with "Reuters said" carrying the load — that is a
  finding. A secondary outlet is a lead, not the spine.

**Preferred outcome:** it reads like one person who understands the subject explaining it
once, well.

## 6. Do the figures earn their place?

**The vulnerability.** A chart gets requested because the story has numbers in it, not
because a figure would tell the reader something prose cannot.

- **Does it answer a question?** A timeline of dates the prose already gave is not a
  finding. If the figure adds nothing, say so — removing it is a legitimate outcome.
- **Is it legible in about three seconds?** A title that states the finding rather than the
  measure, series labelled directly rather than via a legend, the story's number annotated
  where it happens.
- **Are the units and status clear?** "279 total DUV systems, 47% immersion" told a reader
  nothing: not what a DUV system is, not whether 279 was a year or a total, not whether the
  bars beside it were actual output or an announced target. Every number needs its unit in
  plain words and its status marked — actual, reported, estimated, or *target*.
- **Are the compared things comparable?** A subset plotted against a total silently
  overstates a gap.
- **Does the caption speak to the reader?** Not to us, and not restating the title.

**Preferred outcome:** a reader glances at the figure and immediately knows more than they
did.

## 7. Is the furniture right?

**The vulnerability.** Metadata is assigned from the profile's declared facts, before anyone
has read the finished article, so nothing upstream can tell whether the prose accounts for it.

- **Country flags.** A flag beside the headline is the reader's first orientation cue, and an
  unearned one is a question we raise and never answer — a shipped piece flew a South Africa
  flag with the country unmentioned anywhere. A country belongs if something happens there,
  an institution or government of it acts, or people there bear a consequence. A wire filing
  *from* a city is not enough; neither is an agency merely being headquartered there.
- **Names spelled correctly and in full at first use.** A published piece opened "NASA's
  Neil Swift Observatory" — the actual name is the *Neil Gehrels* Swift Observatory, and the
  article's own tags had it right. Garbled proper nouns, mangled institution names and
  dropped name-parts are cheap to catch here and corrosive to trust.
- **Numbers consistent between prose, caption and figure.** If they disagree, the piece is
  wrong somewhere and a reader who notices stops believing the rest.

**Preferred outcome:** nothing on the page raises a question the page does not answer.
