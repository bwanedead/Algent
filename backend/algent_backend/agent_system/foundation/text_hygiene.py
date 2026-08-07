"""
Control characters must never reach a contract, an artifact, or a URL.

A live synthesis run wrote 333 NUL bytes into its portfolio — one wherever an em dash
should have been. The model was not at fault: its own turn log carries the em dash, and a
direct structured-output call to the same model round-trips ``—``, ``ü`` and ``°`` intact.
Something between the response and the validated object substitutes U+0000 for that
character, and the root cause is still open.

What is NOT open is that a NUL in our data is always wrong, and gets worse the further it
travels:

- it reached article front-matter as ``title: "...breathe \\094 and why..."``;
- it reached a published **slug**, which is a permanent URL —
  ``the-microscopic-hairs-that-let-corals-breathe-94-and-why-hea``. A slug cannot be
  corrected later without breaking every link to it;
- it renders as nothing, so prose silently loses its punctuation and reads as a gap.

So this scrubs at the boundary rather than waiting for a root cause. It is deliberately
conservative: it removes only C0 control characters that have no business in prose, and
never tries to guess what a NUL replaced. Restoring an em dash would be a plausible repair
for the one corruption we have measured, and a fabrication in every case we have not.
"""

from __future__ import annotations

import re
from typing import Any

#: C0 controls except tab and newline, which are legitimate in a body. NUL is the one we
#: have actually seen; the rest are in the same class and equally unwanted in text.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def scrub_text(value: str) -> str:
    """Strip control characters and tidy the whitespace their removal leaves behind."""
    if not value or not _CONTROL.search(value):
        return value
    out = _CONTROL.sub("", value)
    # A removed NUL usually sat between words ("Nonthaburi \x00 rare"), so dropping it
    # leaves a double space. Collapse runs, but never touch newlines.
    out = re.sub(r"[ \t]{2,}", " ", out)
    return re.sub(r" +([,.;:!?])", r"\1", out).strip()


def scrub(value: Any) -> Any:
    """Recursively scrub strings inside dicts/lists/tuples. Other types pass through."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, tuple):
        return tuple(scrub(v) for v in value)
    return value


def has_control_chars(value: str) -> bool:
    """Did model output arrive with control characters? Worth reporting, not just fixing."""
    return bool(value) and bool(_CONTROL.search(value))
