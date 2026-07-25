"""
Hero-image briefs — the prompt for an article's opening illustration, built safely.

The image's job is narrow: convey *what the piece is about* at a glance, so the article
does not open as a wall of text and so a link posted elsewhere carries a picture. It is
**decoration and orientation, never evidence**, and everything here exists to keep that
line intact.

Why it is built from a subject rather than from the headline
-----------------------------------------------------------
Passing the headline straight to an image model is the obvious approach and it fails
badly. Observed, from three real generations:

- *"orca whale swimming, stock photo style"* → a clean, useful photograph-style orca.
- The T. rex headline, passed verbatim → a usable illustration with the entire headline
  **rendered as text inside the image**, which locks the picture to wording that later
  changes and looks like a meme card.
- The Florida headline, passed verbatim → an infographic containing a **fabricated
  Bureau of Economic Analysis seal**, the words "DATA CONFIRMED", and an invented
  ranking chart putting California 1st, Texas 2nd and Florida 14th. The article's claim
  was 14th *among countries*; the picture asserted something else entirely, in the
  visual language of an official source.

That last one is the whole reason this module is defensive. An image model handed
numbers will draw numbers, and drawn numbers look like data. A newsroom that keeps
receipts cannot publish a synthetic government seal over figures it did not verify.

So: the model is given a **concrete physical subject** and never the headline, never a
figure, never an institution's name. The prohibitions are appended in code, not left to
a prompt author to remember.
"""

from __future__ import annotations

import re

# Every hero image says what it is, wherever it appears. Non-negotiable: a generated
# picture beside a news story is a lie unless it is labelled one.
IMAGE_LABEL = "AI-generated illustration — not a photograph of this story"

# What we want: the visual register of a stock editorial photograph. Plain and legible at
# thumbnail size, because that is how it will be seen on a feed or a shared link.
_STYLE = (
    "editorial stock-photograph style, natural lighting, clean uncluttered composition, "
    "wide 16:9 landscape framing, safe for work"
)

# Appended to every prompt, in code. Each clause is here because of an observed failure or
# an honesty rule we are not willing to leave to chance.
_PROHIBITIONS = (
    "Do not render any text, words, letters, numbers, labels or captions anywhere in the "
    "image. "
    "Do not render charts, graphs, tables, dashboards, infographics, percentages or any "
    "figures or statistics. "
    "Do not render logos, seals, crests, badges, flags-as-insignia, watermarks or anything "
    "resembling an official emblem or government mark. "
    "Do not depict a recognisable real, identifiable person. "
    "Do not stage it as documentary or news photography of a specific real event, and do "
    "not imply it is a photograph of the events described. "
    "A generic, representative illustration of the subject is exactly what is wanted."
)

# A subject carrying digits, money or percentages invites the model to draw data — which is
# how the fabricated BEA chart happened. Reject rather than sanitise: a subject that needs a
# number is a subject that has not been reduced to something depictable.
_QUANTITY = re.compile(r"[0-9%$€£¥]|\b(?:per ?cent|percent|trillion|billion|million|rank(?:ed|ing)?)\b", re.I)

# Words that mean "draw me a document/figure". Same reasoning.
_ARTEFACT = re.compile(
    r"\b(?:chart|graph|table|infographic|dashboard|map|diagram|logo|seal|headline|report|"
    r"screenshot|document|data)\b",
    re.I,
)

MAX_SUBJECT_WORDS = 14


class UnsafeImageSubject(ValueError):
    """The subject would push the model toward drawing data, text, or an official artefact."""


def check_subject(subject: str) -> str | None:
    """Return the reason this subject is unusable, or ``None`` when it is fine."""
    text = (subject or "").strip()
    if not text:
        return "empty subject"
    if len(text.split()) > MAX_SUBJECT_WORDS:
        return f"too long ({len(text.split())} words) — reduce to the physical thing being shown"
    if _QUANTITY.search(text):
        return "contains a quantity; a subject with numbers in it gets numbers drawn into the image"
    if _ARTEFACT.search(text):
        return "names a chart/document/logo; hero images are illustrations, never data or artefacts"
    return None


def is_safe_subject(subject: str) -> bool:
    return check_subject(subject) is None


def build_image_prompt(subject: str, *, setting: str = "") -> str:
    """Assemble the generation prompt for a hero image. Raises on an unusable subject.

    ``subject`` is the concrete physical thing to depict ("an orca surfacing in coastal
    water", "a juvenile feathered tyrannosaur"). ``setting`` optionally places it. The
    headline is deliberately not a parameter — see the module docstring.
    """
    reason = check_subject(subject)
    if reason is not None:
        raise UnsafeImageSubject(f"{subject!r}: {reason}")
    scene = f"{subject.strip()}, {setting.strip()}" if setting.strip() else subject.strip()
    return f"{scene}. {_STYLE}. {_PROHIBITIONS}"


# -- the review gate ----------------------------------------------------------
#
# Prompting reduces these failures; it does not eliminate them. An image model will still
# occasionally letter a word onto a sign, or draw something that is not the subject at all.
# So a generated image is checked before it can be attached, by a vision model looking for
# exactly the failure classes we have already seen — not for aesthetics.

IMAGE_REJECTIONS: tuple[str, ...] = (
    "text_in_image",        # any rendered words, letters, numbers or captions
    "chart_or_data",        # a chart, graph, table, infographic or figures presented as data
    "official_insignia",    # a logo, seal, crest, badge or watermark — real or invented
    "identifiable_person",  # a recognisable real person
    "reads_as_documentary", # staged so a reader would take it for a photo of the real event
    "off_subject",          # not the thing the article is about
    "unsafe_content",       # gore, sexual content, or otherwise unpublishable
)

IMAGE_REVIEW_PROMPT = """\
You are checking a generated illustration before it is attached to a news article. You are
NOT judging whether it is attractive. You are answering one question: would publishing this
beside the article mislead a reader?

The image should be a plain, representative illustration of its subject. Reject it if you see:

- text_in_image — any rendered words, letters, numbers, labels or captions at all, including
  on signs, screens or documents inside the scene.
- chart_or_data — a chart, graph, table, dashboard or infographic, or any figures shown as
  though they were data. This is the most serious one. A picture of a chart is a claim, and a
  generated chart is a claim we did not verify.
- official_insignia — a logo, seal, crest, badge, watermark or government-style emblem,
  whether or not it copies a real one. An invented official seal is a forged document.
- identifiable_person — a recognisable real individual.
- reads_as_documentary — framed so a reader would take it for an actual photograph of the
  specific events described, rather than a generic illustration.
- off_subject — it does not depict what the article is about.
- unsafe_content — gore, sexual content, or otherwise unpublishable.

Report every failure you find with the region or element that triggered it. When the image is
a clean generic illustration of its subject and carries none of the above, pass it.
"""
