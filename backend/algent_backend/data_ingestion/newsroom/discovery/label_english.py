"""
English menu labels for the t0 pool.

We happily source non-English leads (beats, GKG languages, world wires). The operator
menu must still be triageable in English: keep the original label, and when it is not
English, attach ``signals.label_en``. Article output stays English-central elsewhere
(drafter doctrine) — this module only makes the pick-list readable.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any

from .crystallize import HouseCrystallizeClient
from .report import DiscoveryPool, PoolItem

ProgressFn = Callable[[str], None]

_ENV_ON = "ALGENT_T0_MENU_EN"  # 0/false to skip
_ENV_MODEL = "ALGENT_T0_MENU_EN_MODEL"

# Scripts that almost never appear in English-central headlines.
_NON_LATIN = re.compile(
    r"["
    r"\u0400-\u04FF"  # Cyrillic
    r"\u0600-\u06FF"  # Arabic
    r"\u0900-\u097F"  # Devanagari
    r"\u0980-\u09FF"  # Bengali
    r"\u0E00-\u0E7F"  # Thai
    r"\u3040-\u30FF"  # Hiragana / Katakana
    r"\u3400-\u9FFF"  # CJK
    r"\uAC00-\uD7AF"  # Hangul
    r"\u0590-\u05FF"  # Hebrew
    r"\u10A0-\u10FF"  # Georgian
    r"\u0370-\u03FF"  # Greek
    r"]"
)


def menu_english_enabled() -> bool:
    return os.environ.get(_ENV_ON, "1").strip().lower() not in ("0", "false", "no", "off")


def looks_non_english(label: str) -> bool:
    """Cheap prefilter: non-Latin script, or heavily accented Latin."""
    text = (label or "").strip()
    if not text:
        return False
    if _NON_LATIN.search(text):
        return True
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    non_ascii = sum(1 for c in letters if ord(c) > 127)
    return non_ascii >= max(3, len(letters) // 4)


def enrich_english_labels(
    pool: DiscoveryPool,
    *,
    on_progress: ProgressFn | None = None,
) -> DiscoveryPool:
    """Attach ``signals.label_en`` for non-English labels. No-op when paused / no key."""
    say = on_progress or (lambda _m: None)
    if not menu_english_enabled():
        say("menu-en: paused (ALGENT_T0_MENU_EN=0)")
        return pool

    need: list[PoolItem] = []
    for item in pool.items:
        sig = item.signals or {}
        if sig.get("label_en"):
            continue
        if looks_non_english(item.label) or _latin_maybe_foreign(item.label):
            need.append(item)
    if not need:
        say("menu-en: nothing to translate")
        return pool

    client = _try_house_client()
    if client is None:
        say(
            f"menu-en: no model key — flagging "
            f"{sum(1 for i in need if looks_non_english(i.label))} non-Latin labels"
        )
        return _flag_only(pool, need)

    say(f"menu-en: translating {len(need)} candidate labels…")
    try:
        mapping = _translate_batch(client, need)
    except Exception as exc:  # noqa: BLE001 — menu English must not sink t0
        say(f"menu-en: LLM failed ({str(exc)[:80]}); flagging scripts only")
        return _flag_only(pool, need)

    updated: list[PoolItem] = []
    applied = 0
    for item in pool.items:
        en = mapping.get(item.id)
        if not en:
            updated.append(item)
            continue
        en = en.strip()
        if not en or en == item.label.strip():
            updated.append(item)
            continue
        sig = dict(item.signals or {})
        sig["label_en"] = en[:300]
        updated.append(item.model_copy(update={"signals": sig}))
        applied += 1
    usd = getattr(client, "last_usd", 0.0) or 0.0
    say(f"menu-en: attached {applied} English labels (~${usd:.4f})")
    return pool.model_copy(update={"items": updated})


def format_menu_label(item: dict[str, Any] | PoolItem) -> tuple[str, str | None]:
    """Return (display_english_or_label, original_if_different)."""
    if isinstance(item, PoolItem):
        label = item.label or ""
        en = (item.signals or {}).get("label_en")
    else:
        label = str(item.get("label") or "")
        en = (item.get("signals") or {}).get("label_en")
    en_s = str(en).strip() if en else ""
    if en_s and en_s != label.strip():
        return en_s, label
    return label, None


def _latin_maybe_foreign(label: str) -> bool:
    """Latin-script headlines that still often need translation (IT/ES/NL/TR/ID/…)."""
    text = (label or "").strip()
    if not text or _NON_LATIN.search(text):
        return False
    if not any(c.isalpha() and ord(c) < 128 for c in text):
        return False
    tokens = re.findall(r"[A-Za-z']+", text.lower())
    if len(tokens) < 3:
        return True
    english_glue = {
        "the", "a", "an", "of", "in", "on", "for", "to", "and", "or", "as", "is", "are",
        "was", "were", "be", "by", "with", "from", "at", "that", "this", "it", "its",
        "will", "has", "have", "had", "not", "but", "after", "before", "over", "under",
        "into", "about", "than", "then", "who", "what", "why", "how", "says", "said",
        "new", "us", "u", "s",
    }
    glue_hits = sum(1 for t in tokens if t in english_glue)
    return glue_hits < max(1, len(tokens) // 5)


def _flag_only(pool: DiscoveryPool, need: list[PoolItem]) -> DiscoveryPool:
    need_ids = {i.id for i in need if looks_non_english(i.label)}
    updated: list[PoolItem] = []
    for item in pool.items:
        if item.id not in need_ids:
            updated.append(item)
            continue
        sig = dict(item.signals or {})
        if not sig.get("label_en"):
            sig["label_en_missing"] = True
        updated.append(item.model_copy(update={"signals": sig}))
    return pool.model_copy(update={"items": updated})


def _translate_batch(client: HouseCrystallizeClient, items: list[PoolItem]) -> dict[str, str]:
    payload = [{"id": i.id, "label": i.label} for i in items]
    system = (
        "You translate newsroom discovery menu labels into clear English.\n"
        "For each input that is NOT already English, return "
        '{"id":"...","en":"..."}.\n'
        "Skip labels that are already English. Keep proper names. "
        "One short English headline or sentence; same meaning; no commentary.\n"
        'Respond as JSON object: {"translations":[...]}'
    )
    user = json.dumps({"labels": payload}, ensure_ascii=False)
    rows = client.complete_json(system=system, user=user)
    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        iid = str(row.get("id") or "").strip()
        en = str(row.get("en") or row.get("english") or row.get("label_en") or "").strip()
        if iid and en:
            out[iid] = en
    return out


def _try_house_client() -> HouseCrystallizeClient | None:
    try:
        from algent_backend.agent_system.foundation.models import house_provider
        from algent_backend.config import get_provider_api_key
        if not get_provider_api_key(house_provider()):
            return None
    except Exception:  # noqa: BLE001
        return None
    from algent_backend.agent_system.foundation.models import house_model_id, house_spec

    model = (os.environ.get(_ENV_MODEL) or "").strip() or house_model_id()
    return HouseCrystallizeClient(
        house_spec(reasoning_effort="low", temperature=0.1, model=model)
    )
