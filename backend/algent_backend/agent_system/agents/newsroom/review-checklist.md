# The Review Register

The accumulated list of things that have actually gone wrong in published pieces, what
each one costs a reader, and what we want instead.

This file is the newsroom's memory of its own failures. Every entry earned its place by
shipping — none is hypothetical. It exists because the same defects kept reappearing after
being "fixed" upstream: doctrine was added to the drafter, the next article did it again,
and nobody was checking. **The review stage is where we verify that our fixes held.**

## How to use it

Work the register. Not "read the piece and see if anything feels off" — that is how UVOT
shipped six times in one article. Go through the sections below against the finished piece,
then write the next draft when it does not land. A clean piece producing no findings (and
no rewrite) is the expected outcome for good work; manufacturing stumbles to look diligent
is its own failure.

Two standing rules on your powers:

- **You write the next draft when it does not land.** Diagnose in findings, then emit
  title, standfirst, and body as the piece a cold reader should have been handed — same
  facts already on the page. Do not send notes back to the drafter.
- **You may make the piece clearer, never stronger.** Clarify, cut, reorder, restate from
  the reader's side. Never invent a claim, assert harder, or write toward length.
- **Padding is a failure, not a fix.** Getting shorter is success. A hollow stub is not.

## Why review is bounded

You rewrite, a **fresh instance** reads that rewrite, and if it still does not land you
rewrite once more and it publishes anyway, with the findings on record. This is deliberate:
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

**Preferred outcome:** a reader who reads only the headline knows what the piece is about; the
headline + standfirst together still convey why somebody would care and any load-bearing limit.
The title is a crisp wrapper, not a caveat compound.

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
  showing it. The fix is to **cut** the label, never to add emphasis;
- **the craft narrated to the reader** — the writer describing what the writing is doing.
  Shipped: *"The reader needs only a few footholds to follow it"* opening a paragraph that
  then supplied them; also *"Europe's electricity grid … is the through-line"* and a closing
  line admiring the piece's own two figures. Handing over footholds is right; **saying** you
  are about to is the doctrine leaking through the prose. A reader is not a student being
  told the lesson plan. The fix is always to delete the sentence and keep what follows it —
  the footholds themselves lose nothing.

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
- **Lead-as-article.** If the piece's subject is that a podcast / wire / hearing / blog
  *mentioned* a finding, and the body is mostly verification-gap narration about that
  mention rather than an explanation of the underlying claim, that is a finding — even when
  every sentence is carefully hedged. Hedging a thin meta-piece does not make it journalism.
  Prefer: cut research-state / "we could not verify" narration that is doing the spine's job;
  rewrite so the outlet mention is evidence or provenance, not the subject; record the
  structural miss clearly for the next enrichment lap. Do not invent the missing landscape
  in this pass.

- **Sentences that need re-reading.** Some published sentences cannot be parsed by their
  intended reader at any speed. Shipped verbatim:

  > Ambient-noise tomography images Vs, not melt. Converting Vs to melt fraction and volume
  > is the most assumption-dependent step.

  Two sentences, four pieces of unexplained apparatus, and a reader who now knows only that
  they are not the audience. **Read every sentence once, at speed, as the reader.** If you
  would have to go back, it fails — and the fix is a lower ramp into the idea, not a shorter
  sentence. That example wants something like: *the method measures how fast waves travel,
  not how much rock is molten, so turning one into the other is where the estimate is
  softest.* Same content, no apparatus, one pass.
- **Whiplash pivots.** Chunks that are well written in isolation and then hand off to
  something unrelated with no bridge. The reader is building a model as they go; an
  unheralded turn makes them drop it. Every new idea arrives *attached* to the one before it.
- **Section proliferation.** Five headed sections inside one article is a symptom, not a
  structure — usually the research profile's shape showing through. Headings are for a piece
  that genuinely has parts; most of ours do not. Prefer continuous prose that carries the
  reader by argument rather than by signposts, and treat every heading as needing to earn
  itself. Chopping a piece into labelled blocks is the cheap way to look organised and it
  reads as low-effort assembly.

**Preferred outcome:** it reads like one person who understands the subject explaining it
once, well — continuous, in one voice, with no sentence that needs a second pass.

## 5b. Is it about the forest or the twigs?

**The vulnerability.** Research gathers method and detail, so the draft narrates the method
and detail. The reader wanted to know what it means for anything.

A published piece on perovskite-on-silicon solar cells never established that the subject was
**making solar panels cheaper or more efficient**, never explained what the technique is for
in any broader sense, and spent its length walking through procedure. Every sentence may have
been true and the piece was still useless: a reader finished it unable to say why they had
read it.

- **Say what it is for, early and plainly.** Before any apparatus: what does this technology,
  method or finding *do* in the world, and who would notice if it worked?
- **Detail must be load-bearing.** A number, a step, a parameter earns its place only if it
  changes what the reader concludes. Procedure that merely shows the work belongs in the
  appendix, which we already publish.
- **Ratio test.** Roughly, how much of this piece is *significance and consequence* versus
  *method and peripheral detail*? If the second dominates, it is a walkthrough, not an article.
- **Not a word cap.** The fix is never "make it shorter" — it is cutting the twigs so the
  forest is visible. A long piece that stays on the through-line is fine; a short one buried
  in procedure is not.
- **Resolution check: is this worth what it costs the reader?** The most reliable source of
  length is not padding but *grain* — particulars carried finer than the reader will ever use.
  A border piece named six friction points with their disengagement dates; a reader holds
  "three main stretches of contested border, one cluster now managed" and could not name one of
  the six an hour later. For every collection, say which of three applies: the detail carries
  weight alone (it recurs, the story turns on it, it is evidence for a contested claim) — keep
  it; the meaning is at the collection layer — name the collection, not the members; the
  collection would not change what the reader takes away — cut it, leaving at most a clause
  that the direction exists.
- **Is the mechanism explained past what the reader can use?** The most reliable overshoot, and
  the one that hides best, because depth reads as rigour and the research supports every word. A
  piece on printing chips with a particle accelerator opened well — the pitch, the claim, the
  stakes — then spent itself on tin-plasma EUV physics and free-electron laser mechanics. Flag
  it: the target is what the development **means** for the world the reader already lives in,
  not a lecture on the apparatus. A rough idea of what it relies on is enough. Flag as
  `lecture` (`cut` the excess, or `rewrite_for_reader` to the meaning sentence if it is not
  already elsewhere). Completeness governs the shape (the sides, the caveats, the contrary
  evidence), never the resolution of an explanation. Do not accept "but it's all true and
  sourced" as an answer; that was never the question.
- **Look for a whole section that could be one sentence.** This is the biggest available win
  and the one reviewers keep missing while catching smaller things. A section walking every
  component of a tension can usually become *that the tension exists, between whom, and why it
  is unresolved*. Go section by section and ask what each one establishes; where the answer is
  a sentence, say so and name the section. Six well-merged concepts written as six long
  sections is the same overlong article by another route — a piece can pass every upstream
  check and still spend the reader's attention on enumeration.
- **Run the compression pass, and name what you cut.** Not a word cap, but not a pass you may
  skip either: pieces on the through-line still land several hundred words heavy, because the
  padding arrives disguised as care. Check the five patterns in
  [writing-ergonomics](writing-ergonomics.md) — *the top of the piece saying one fact three
  times* (dek, At-a-glance, opening paragraph, written by different stages and converged
  without anyone noticing), mid-sentence glosses, one magnitude framed three ways, full
  institutional titles, second units and hedge tails. Make those cuts in the rewrite; name
  them in findings. A reviewer who says "reads well" about a piece carrying all five
  has confirmed prose quality and missed the problem.

**Preferred outcome:** a reader can say what this changes, for whom, and why it was worth
their time — and the detail they remember is the detail that supports that.

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
