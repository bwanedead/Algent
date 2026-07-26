"""
The hero-image stage — turn the headline writer's brief into a file in the run's artifacts.

Sits immediately after the headline because that is where ``image_subject`` and
``image_hook`` are written, by the one stage that has read the finished piece.

Everything about this stage is designed to be *skippable*. A hero is decoration: it helps
an article not open as a wall of text and it gives a shared link something to show. Nothing
about the journalism depends on it. So every failure path — no key, no subject, a guard
refusal, a dead API — returns ``None`` and the article publishes exactly as it would have
before. It must never be able to cost us a run.

On by default (``ALGENT_HERO_IMAGE=0`` to disable). It spends ~$0.034 per article on the
lite model, which is a few percent of a rail, and an article without an opening picture is
a wall of text and a shared link with nothing to show — worth more than the cost.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from .hero_image import IMAGE_LABEL, UnsafeImageSubject, check_hook, check_subject

_ENV_ON = "ALGENT_HERO_IMAGE"
HERO_STEM = "hero"


@dataclass(frozen=True)
class HeroRecord:
    """What the pipeline reports and the publisher needs. Mirrors the artifact on disk."""

    artifact_name: str
    alt: str                 # the subject, which is also the honest description of the picture
    hook: str                # words set on the image, empty for a plain one
    label: str
    model: str
    size: str
    estimated_usd: float


def hero_enabled() -> bool:
    return os.environ.get(_ENV_ON, "1").strip().lower() not in ("0", "false", "no", "off")


def make_hero(
    headline: dict[str, Any],
    artifacts: Any,
    *,
    say: Any = None,
    generate: Any = None,
) -> dict[str, Any] | None:
    """Generate the hero for a finished piece, or return None. Never raises.

    ``artifacts`` is the run's ArtifactWriter (None when a run has no artifact sink);
    ``generate`` is injected so tests never reach the network.
    """
    note = say if callable(say) else (lambda _m: None)
    if not hero_enabled() or artifacts is None:
        return None

    subject = str(headline.get("image_subject") or "").strip()
    hook = str(headline.get("image_hook") or "").strip()
    if not subject:
        # The headline writer is told to leave this empty when a piece has no depictable
        # subject. That is a decision, not a gap — no image beats a misleading one.
        note("hero: no image subject for this piece — skipped")
        return None

    # Check before spending. A guard refusal here is the headline writer having written a
    # subject or hook it was told not to, which is worth surfacing rather than swallowing.
    for label, reason in (("subject", check_subject(subject)), ("hook", check_hook(hook))):
        if reason is not None:
            note(f"hero: {label} rejected ({reason}) — skipped")
            return None

    try:
        from .image_gen import generate_hero_image

        fn = generate or generate_hero_image
        image = fn(subject, hook=hook)
    except UnsafeImageSubject as exc:
        note(f"hero: refused ({str(exc)[:100]}) — skipped")
        return None
    except Exception as exc:  # noqa: BLE001 — decoration must never cost us the article
        note(f"hero: generation failed ({type(exc).__name__}: {str(exc)[:90]}) — skipped")
        return None

    name = f"{HERO_STEM}{image.suffix()}"
    try:
        artifacts.write_bytes(name, image.data, kind="image")
    except Exception as exc:  # noqa: BLE001
        note(f"hero: could not write artifact ({str(exc)[:80]}) — skipped")
        return None

    record = HeroRecord(
        artifact_name=name, alt=subject, hook=hook, label=IMAGE_LABEL,
        model=image.model, size=image.size, estimated_usd=image.estimated_usd,
    )
    note(
        f"hero: {name} ({image.size}, {image.model.split('-')[-2]}) "
        f"~${image.estimated_usd:.4f}" + (f' — "{hook}"' if hook else " — no caption")
    )
    return asdict(record)
