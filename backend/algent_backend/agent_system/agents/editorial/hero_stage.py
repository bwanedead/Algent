"""
The hero-image stage — turn the headline writer's brief into a file in the run's artifacts.

Sits immediately after the headline because that is where ``image_subject`` and
``image_hook`` are written, by the one stage that has read the finished piece.

House policy (current default): **every article gets a hero** — a thumbnail-style stage-
setting image for the topic's substance, not evidence. Generation/API failure still returns
``None`` so decoration can never sink a run. An empty or unsafe ``image_subject`` falls back
to a neutral stage-setting (never invents a scene from the title — that could depict a
disputed claim the writer declined to illustrate). Opt out with ``ALGENT_HERO_IMAGE=0``.

On by default. It spends ~$0.034 per article on the lite model, which is a few percent of a
rail, and an article without an opening picture is a wall of text and a shared link with
nothing to show — worth more than the cost.
"""

from __future__ import annotations

import os
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
) -> dict[str, Any] | None:
    """Generate the hero for a finished piece, or return None. Never raises.

    ``artifacts`` is the run's ArtifactWriter (None when a run has no artifact sink);
    ``generate`` is injected so tests never reach the network.
    """
    note = say if callable(say) else (lambda _m: None)
    if not hero_enabled() or artifacts is None:
        return None

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
            note(f"hero: skipped ({cost.mode()} — budget)")
            return None
        fn = generate or generate_hero_image
        try:
            image = fn(subject, hook=hook)
        except Exception:
            cost.release(res)
            raise
        cost.settle(res, float(getattr(image, "estimated_usd", est) or est))
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
