# Information ergonomics — how Ohmega's pages put the world into a reader's head

Operator brief (2026-10-02): not flash, maximal usage. Information should "download into the brain":
minimal, utilitarian, far more visual, the eye guided to what matters. This is the doctrine every
reader-facing surface (site pages, briefs, daily reports, Pulse views) is built and reviewed against.
Each rule names the finding it rests on, so it can be argued with on evidence, not taste.

## The order of a page: overview → zoom → detail

**Overview first, zoom and filter, details on demand** (Shneiderman, 1996). Every page opens with one
screen that answers "what is the state, and what changed?" without scrolling or reading paragraphs.
Detail exists, but it waits behind a deliberate action (open a popover, open a section). If the first
screen needs prose to be understood, the page has failed.

**Bottom line up front.** Each unit (page, theater, brief) leads with its single takeaway as a
sentence that carries the finding: "Hormuz still shut; no US reply", not "Developments". Headings are
claims, not category labels. Readers scan headings and first words (eye-tracking: the F / layer-cake
patterns, NN/g); a label heading wastes the one look they give it.

## Budget the reader's working memory

Working memory holds about **four chunks** (Cowan, 2001). So:
- at most ~4–5 items per group on a first screen (top movers, theaters, bullets); the rest one click away;
- group related things into one chunk with a visible shape (a row, a card) so they cost one slot, not five;
- never make the reader hold a number while hunting for its meaning: the scale travels with the
  number (spectrum, axis, "of 100"), the comparison travels with the change (from → to).

## Spend pre-attentive attention on one meaning each

Colour, size, position, motion and contrast are seen in under ~250 ms, before reading (Treisman;
Healey & Enns). That budget is tiny, so each channel gets ONE meaning, site-wide:
- **Band colour = severity**, and only severity (Pulses). Never decorative, never for coverage.
- **The accent = change / new.** Whatever moved since the last reading or the reader's last visit is the
  only thing that wears it. Everything else is quiet.
- **Size = importance** (bigger number, bigger move). **Position = rank** (first is most important).
- Neutral greys carry structure. If two things on a screen shout, neither is heard.

## Encode quantities the way eyes measure best

Accuracy of visual judgement, best to worst: **position on a common scale → length → angle/slope →
area → colour intensity** (Cleveland & McGill, 1984). So:
- compare Pulses on a **shared 0–100 axis** (dot or bar on one scale), not as separate gauges;
- show change as **from → to** on the same axis (a dumbbell / arrow), or as a diverging bar around zero;
- no pies, no 3-D, no area-for-quantity; colour intensity is never the only carrier of a number.

**Small multiples** (Tufte): when several things are compared, draw them all in the same shape, same
scale, side by side, so the eye learns the chart once and reads the differences. **Data-ink**: remove
borders, boxes, rules and labels that carry no data; use whitespace and alignment (Gestalt proximity
and common region) to group instead of lines.

## Pair words with pictures

People remember and understand better when a claim arrives as words **and** an image (dual coding,
Paivio; Mayer's multimedia principle). Every important claim on a page should have its picture: where
(map), how much (figure against a baseline), which way and how fast (sparkline, arrow), who acts on whom
(relation), when (timeline). If a section is only text, ask which picture it is missing.

## Make change impossible to miss

People are bad at noticing change between two views (change blindness, Simons & Rensink). The
machine knows what changed; the page must say it explicitly: deltas with arrows and signs, "since
yesterday" lists, "new since your last visit" markers, before → after. A number without its change is
half a reading.

## One interaction grammar, everywhere

Consistency lets readers spend attention on content, not on learning controls (Jakob's law). Site-wide:
- **Details open in a popover layered over the page** (a bottom sheet on phones). The page never
  reflows, never navigates away, never loses the reader's place. Esc / outside click / × closes it.
  One open at a time. Deep links can open it.
- The same object looks and behaves the same everywhere: a Pulse is always the same tile (name, number,
  meter) and always opens the same popover.
- Few controls, each obvious (Hick's law): defaults that answer the common question; options hidden
  until wanted.

## Trust is part of the picture

The legibility of trust is information too (brand: maximum information + legible trust level). Mark,
consistently and quietly: researched vs reported, the grade of a claim, "early reading", forecast
probability, as-of dates. Quiet means a small consistent marker, not a warning banner.

## Review checklist (apply to any new or changed surface)

1. Does the first screen answer state + change without scrolling or reading a paragraph?
2. Is every heading a claim? Does each unit lead with its bottom line?
3. ≤ ~5 items per first-screen group? Is the rest behind details-on-demand?
4. Does each colour mean one thing? Is the accent used only for change/new?
5. Are compared quantities on a shared scale, by position or length?
6. Does every important claim have its picture?
7. Is change shown explicitly (from → to, Δ, since-yesterday, new-since-last-visit)?
8. Do details open in the shared popover, without reflow?
9. Can any border, box, label or rule be deleted without losing information? Delete it.
