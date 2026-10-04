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

#: The corruption signature, and it is REVERSIBLE — which is why this repairs rather than
#: deletes. Diffing the rake's own input against its output gave the mapping exactly:
#:
#:     '’'  U+2019, UTF-8 e2 80 99   ->   "\x00e2" "\x0080" "\x0099"
#:
#: Every byte of the multi-byte sequence arrives as NUL followed by that byte's two hex
#: digits. That is ``\xe2\x80\x99`` escaping with the ``\x`` prefix replaced by a NUL, so the
#: original character is fully recoverable: read the hex pairs back into bytes and decode.
#:
#: Nothing in this codebase escapes strings that way, short direct calls to the same model
#: never reproduce it, and our own parse path is clean on every variant tested — so this is a
#: provider-side serialisation fault on longer generations. We cannot fix it there; we can
#: undo it exactly here.
_ESCAPED_BYTES = re.compile(r"(?:\x00[0-9a-fA-F]{2})+")

#: C0 controls except tab and newline (both legitimate in a body), plus DEL and the C1
#: block. Applied to whatever survives the repair above — a truncated corruption leaves a
#: bare NUL with no hex to rebuild from, and that must still never reach a slug.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _rebuild(match: re.Match[str]) -> str:
    """Turn a run of NUL+hex back into the character it was before the provider mangled it."""
    pairs = match.group(0)
    try:
        data = bytes(int(pairs[i + 1: i + 3], 16) for i in range(0, len(pairs), 3))
        return data.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        # A partial sequence ("\x00e2" alone) cannot be decoded — drop it rather than
        # emit a replacement character or leave stray hex glued to a word ("Chinab9s").
        return ""


def scrub_text(value: str) -> str:
    """Repair provider-mangled characters, then strip anything unrepairable.

    Repair first: a NUL+hex run carries the original bytes and must be rebuilt before the
    control-stripper eats the NUL and leaves the hex glued to a word ("China’s" would
    otherwise become "Chinab9s", which is worse than the corruption it replaced).
    """
    if not value or not _CONTROL.search(value):
        return value
    out = _ESCAPED_BYTES.sub(_rebuild, value)
    out = _CONTROL.sub("", out)
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
