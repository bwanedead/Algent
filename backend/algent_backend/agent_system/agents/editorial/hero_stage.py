"""
The hero-image stage — turn the headline writer's brief into a file in the run's artifacts.

Sits immediately after the headline because that is where ``image_subject`` and
``image_hook`` are written, by the one stage that has read the finished piece.

House policy: **every article gets a hero** — one Gemini image call per article (~$0.03 on
lite/1K). Empty/unsafe ``image_subject`` falls back to a neutral stage-setting.

**Quota exception:** if Gemini returns 429/quota exhausted, we soft-skip and still publish
(``{"skipped": "quota"}``). That is the only ship-without-hero path while ``ALGENT_HERO_IMAGE``
is on. Other failures hold at publish. Do **not** retry quota errors — retries multiply
burn against a depleted quota for no gain. Opt out entirely with ``ALGENT_HERO_IMAGE=0``.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from typing import Any

from algent_backend.agent_system.foundation import cost

from .hero_image import IMAGE_LABEL, UnsafeImageSubject, check_hook, check_subject
from .image_gen import estimated_usd as hero_est
from .image_gen import generate_hero_image

_ENV_ON = "ALGENT_HERO_IMAGE"
HERO_STEM = "hero"

# Neutral stage-setting when the writer left the subject empty or unsafe. Intentionally
# claim-free — does not invent imagery from the title.
_GENERIC_STAGE = "a quiet landscape under soft daylight"

# Transient server errors only — never retry 429/quota (that doubles spend against an empty pot).
_TRANSIENT_ATTEMPTS = 2
_TRANSIENT_WAIT_S = 3.0


@dataclass(frozen=True)
class HeroRecord:
    """What the pipeline reports and the publisher needs. Mirrors the artifact on disk."""

    artifact_name: str
    alt: str
    hook: str
    label: str
    model: str
    size: str
    estimated_usd: float
    # A real photograph instead of a generated image: its credit rides in the page's hero caption
    # (and the site drops the AI frame, which it decides by the ``photo_`` file name).
    kind: str = "generated"          # generated | photo
    credit: str = ""                 # "Photo: NASA · Public domain · 1982"
    credit_url: str = ""             # the file's Commons page


def hero_enabled() -> bool:
    return os.environ.get(_ENV_ON, "1").strip().lower() not in ("0", "false", "no", "off")


def is_quota_skip(hero: dict[str, Any] | None) -> bool:
    return isinstance(hero, dict) and hero.get("skipped") == "quota"


def resolve_image_subject(headline: dict[str, Any]) -> str:
    """Pick a depictable subject. Prefer the writer's brief; else a claim-free stage-setting."""
    written = str(headline.get("image_subject") or "").strip()
    if written and check_subject(written) is None:
        return written
    return _GENERIC_STAGE


def make_hero(
    headline: dict[str, Any],
    artifacts: Any,
    *,
    say: Any = None,
    generate: Any = None,
    find_photo: Any = None,
) -> dict[str, Any] | None:
    """A real photo of the story's place when one fits; else generate the hero.

    ``find_photo(query, subject) -> (Candidate | None, bytes, note)`` runs first when the writer
    named a real place or thing (``image_photo_query``). A miss costs nothing and falls through.

    Generation returns a quota-skip marker, or None (hold at publish).

    Returns:
      - HeroRecord dict with ``artifact_name`` on success
      - ``{"skipped": "quota"}`` when Gemini quota/429 blocks generation (publish allowed)
      - ``None`` for other failures / budget / disabled (publish holds when enabled)
    """
    note = say if callable(say) else (lambda _m: None)
    if not hero_enabled() or artifacts is None:
        return None

    query = str(headline.get("image_photo_query") or "").strip()
    if query and callable(find_photo):
        photo = _photo_hero(query, headline, artifacts, find_photo, note)
        if photo is not None:
            return photo

    written = str(headline.get("image_subject") or "").strip()
    subject = resolve_image_subject(headline)
    hook = str(headline.get("image_hook") or "").strip()
    if not written:
        note(f'hero: empty image_subject — falling back to "{subject}"')
    elif written != subject:
        note(f'hero: writer subject rejected — falling back to "{subject}"')

    bad_hook = check_hook(hook)
    if bad_hook is not None:
        note(f"hero: hook rejected ({bad_hook}) — generating without caption")
        hook = ""

    try:
        est = hero_est()
        res = cost.try_reserve(est, op="hero_image", essential=True)
        if res is None and cost.is_active():
            note(f"hero: failed ({cost.mode()} — budget); article must not ship without a hero")
            return None
        fn = generate or generate_hero_image
        try:
            image = _call_once_or_transient_retry(fn, subject, hook=hook, note=note)
        except Exception:
            cost.release(res)
            raise
        cost.settle(res, float(getattr(image, "estimated_usd", est) or est))
    except UnsafeImageSubject as exc:
        note(f"hero: refused ({str(exc)[:100]}) — article must not ship without a hero")
        return None
    except Exception as exc:  # noqa: BLE001
        if _is_quota_error(exc):
            note(f"hero: quota/429 — publishing without hero ({str(exc)[:80]})")
            return {"skipped": "quota"}
        note(
            f"hero: generation failed ({type(exc).__name__}: {str(exc)[:90]}) "
            "— article must not ship without a hero"
        )
        return None

    name = f"{HERO_STEM}{image.suffix()}"
    try:
        artifacts.write_bytes(name, image.data, kind="image")
    except Exception as exc:  # noqa: BLE001
        note(f"hero: could not write artifact ({str(exc)[:80]}) — article must not ship without a hero")
        return None

    record = HeroRecord(
        artifact_name=name, alt=subject, hook=hook, label=IMAGE_LABEL,
        model=image.model, size=image.size, estimated_usd=image.estimated_usd,
    )
    # Persist the RECORD beside the image. The bytes alone are not a shippable hero — the
    # publisher needs the alt text and the AI label too, and those lived only in memory and in
    # the pipeline report. When a run died before that report was written, the image survived
    # and its description did not, so a finished article could not be resumed for want of one
    # sentence that nobody could honestly reconstruct.
    try:
        artifacts.write_json("hero.json", asdict(record))
    except Exception as exc:  # noqa: BLE001 — the hero itself is already safely written
        note(f"hero: record not persisted ({str(exc)[:60]}) — resume would lose the alt text")
    note(
        f"hero: {name} ({image.size}, {image.model.split('-')[-2]}) "
        f"~${image.estimated_usd:.4f}" + (f' — "{hook}"' if hook else " — no caption")
    )
    return asdict(record)


def hero_file(artifacts_dir: Any) -> str | None:
    """The hero image in a run's artifacts: the name its record gives, else a ``hero.*`` file.

    Not a bare glob — a real-photo hero is ``photo_hero.*``, and the X post would lose it."""
    from pathlib import Path

    folder = Path(artifacts_dir)
    try:
        import json

        name = str(json.loads((folder / "hero.json").read_text(encoding="utf-8")).get("artifact_name") or "")
        if name and (folder / name).is_file():
            return str(folder / name)
    except Exception:  # noqa: BLE001 — older runs have no record; fall back to the file itself
        pass
    return next((str(p) for p in sorted(folder.glob("hero.*"))
                 if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")), None)


def _photo_hero(query: str, headline: dict[str, Any], artifacts: Any, find_photo: Any,
                note: Any) -> dict[str, Any] | None:
    """The hero as a real photograph, written with its record — or None to generate instead."""
    from .real_images import PHOTO_PREFIX, credit_text, suffix

    subject = str(headline.get("image_subject") or "").strip() or query
    try:
        pick, data, why = find_photo(query, subject)
    except Exception as exc:  # noqa: BLE001 — a failed search falls back to generating
        pick, data, why = None, b"", type(exc).__name__
    if pick is None or not data:
        note(f'hero: no real photo of "{query}" — {why}; generating')
        return None
    name = f"{PHOTO_PREFIX}{HERO_STEM}{suffix(pick)}"
    record = HeroRecord(
        artifact_name=name, alt=pick.description[:200] or subject, hook="", label="",
        model="wikimedia-commons", size="", estimated_usd=0.0,
        kind="photo", credit=credit_text(pick), credit_url=pick.page_url,
    )
    try:
        artifacts.write_bytes(name, data, kind="image")
        artifacts.write_json("hero.json", asdict(record))
    except Exception as exc:  # noqa: BLE001
        note(f"hero: photo not written ({str(exc)[:60]}); generating")
        return None
    note(f"hero: {name} real photo — {pick.title[:70]} ({pick.license})")
    return asdict(record)


def _call_once_or_transient_retry(fn: Any, subject: str, *, hook: str, note: Any) -> Any:
    try:
        return fn(subject, hook=hook)
    except Exception as exc:  # noqa: BLE001
        if _is_quota_error(exc) or not _is_transient(exc):
            raise
        note(f"hero: transient {type(exc).__name__} — one retry")
        time.sleep(_TRANSIENT_WAIT_S)
        return fn(subject, hook=hook)


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(tok in msg for tok in ("429", "quota", "resource_exhausted"))


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, UnsafeImageSubject) or _is_quota_error(exc):
        return False
    msg = str(exc).lower()
    return any(tok in msg for tok in ("unavailable", "timeout", "503", "500", "502"))
