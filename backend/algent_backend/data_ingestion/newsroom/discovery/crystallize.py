"""
Label repair — make machine-derived candidates legible as leads.

GKG does not hand us headlines. It hands us taxonomy codes
(``WB_2811_COLLECTIVE_BARGAINING``), actor×action pairs (``fda :: approve``), and bare
entity names. None of those is a story a human can triage, so a small model rewrites
each into one discrete event sentence — or says it isn't an event at all, and it is
dropped. That is this module's whole remit.

**Scope was deliberately narrowed** (see ITERATION_LOG 2026-07-24). It used to run
over the entire pool and decide keep/drop for everything, which was wrong twice over:

- Most of the pool already *has* a real published headline (every sweep hit, X news,
  a market question). Rewriting those is paraphrase risk for no gain — and it used to
  overwrite ``evidence[0].title``, putting generated text where a real headline had
  been, in the artifact we persist.
- Deciding what is *worth covering* is the synthesis agent's job. It is the capable
  model, it sees the whole pool, and it is instructed to keep the long tail. A cheap
  pre-filter culling the menu ahead of it removes exactly the tail the operator wants
  to see, and does so on less context.

So: items with machine-derived labels are repaired (and dropped if they are not
events); items that already carry a real headline pass through untouched. Structural
junk is still screened for free by the deterministic ``topic_filters`` denylist.

Optional: ``ALGENT_T0_CRYSTALLIZE=0`` skips. Default on when an OpenAI key exists.
Falls back to a conservative heuristic when no key / offline tests.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from ..topic_filters import is_non_news_topic, is_sports_text
from .report import DiscoveryPool, PoolItem

ProgressFn = Callable[[str], None]

_ENV_ON = "ALGENT_T0_CRYSTALLIZE"  # 0/false to skip
_ENV_MAX = "ALGENT_T0_CRYSTALLIZE_MAX"  # items sent to the model (default 40)
_ENV_MODEL = "ALGENT_T0_CRYSTALLIZE_MODEL"

# The triage tier from the house catalog (``foundation.cost.MODEL_PRICES``).
# Crystallize is triage by definition — keep/drop plus a one-sentence rewrite — so
# it belongs on the cheapest current model, not on one of its own choosing. Cost is
# read from that same catalog rather than re-declared here: this file used to carry
# private per-token constants, which meant the ledger stayed wrong independently of
# whatever model was actually called.
_DEFAULT_MODEL = "gpt-5.4-nano"
_DEFAULT_MAX = 40

_SYSTEM = """You are a newsroom discovery filter for a Western generalist desk.

For each candidate, decide if it is a DISCRETE NEWS EVENT worth a reporter's attention today.

KEEP when there is a specific move: who did what to whom/what, with stakes
(strike on named asset, lawsuit filed, ceasefire talks in place X, rate decision,
indictment, export halt, breakthrough confirmation, market-priced political outcome).

DROP when it is:
- standing topic / vague theater ("US armed conflict", "Iran war broadly")
- sports, celebrity, lifestyle, how-to, weather-as-filler, commercial promo
- pure opinion without a new fact-move
- local crime blotter with no national/international stakes
- gardening, product openers, entertainment schedules

For KEEP items write ONE event sentence in English:
  [Actor] [verb past/present] [object/place] [optional stake].
Be specific. Prefer concrete nouns over abstractions. No clickbait.

Return ONLY a JSON array (no markdown), one object per input id:
[{"id":"...","keep":true,"event":"...","reason":"short"},
 {"id":"...","keep":false,"event":null,"reason":"lifestyle"}]
"""


class CrystallizeClient(Protocol):
    def complete_json(self, *, system: str, user: str) -> list[dict[str, Any]]:
        """Return parsed JSON array of decisions."""


@dataclass
class CrystallizeResult:
    kept: int
    dropped: int
    mode: str  # "llm" | "heuristic" | "off"
    estimated_usd: float = 0.0


def crystallize_enabled() -> bool:
    raw = os.environ.get(_ENV_ON, "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def crystallize_pool(
    pool: DiscoveryPool,
    *,
    client: CrystallizeClient | None = None,
    on_progress: ProgressFn | None = None,
    max_items: int | None = None,
) -> tuple[DiscoveryPool, CrystallizeResult]:
    """Rewrite/drop pool items into event-shaped leads. Never raises out."""
    say = on_progress or (lambda _m: None)
    if not crystallize_enabled():
        return pool, CrystallizeResult(kept=len(pool.items), dropped=0, mode="off")

    items = list(pool.items)
    if not items:
        return pool, CrystallizeResult(kept=0, dropped=0, mode="off")

    cap = max_items if max_items is not None else _int_env(_ENV_MAX, _DEFAULT_MAX, 10, 80)
    # Only what needs repairing goes to the model. Everything else already reads as a
    # lead and is none of this module's business.
    repairable = [i for i in items if _needs_label_repair(i)]
    ranked = _priority_order(repairable)[:cap]
    rest = [i for i in items if i.id not in {r.id for r in ranked}]
    if not ranked:
        # Nothing machine-labelled this cycle (a pool that is all real headlines is a
        # good pool). Don't pay for a call with an empty payload.
        say("crystallize: nothing needs label repair — skipped")
        return pool, CrystallizeResult(kept=len(items), dropped=0, mode="off")

    llm = client or _try_openai_client()
    if llm is not None:
        try:
            decisions, usd = _llm_decide(llm, ranked, say)
            mode = "llm"
        except Exception as exc:  # noqa: BLE001 — crystallizer must not sink t0
            say(f"crystallize: LLM failed ({str(exc)[:80]}); heuristic fallback")
            decisions, usd = _heuristic_decide(ranked), 0.0
            mode = "heuristic"
    else:
        say("crystallize: no model key — heuristic filter only")
        decisions, usd = _heuristic_decide(ranked), 0.0
        mode = "heuristic"

    by_id = {d["id"]: d for d in decisions if isinstance(d, dict) and d.get("id")}
    kept_items: list[PoolItem] = []
    dropped = 0
    for item in ranked:
        d = by_id.get(item.id)
        if d is None:
            # Model skipped this id — keep original (safe).
            kept_items.append(item)
            continue
        if not d.get("keep", False):
            dropped += 1
            continue
        event = str(d.get("event") or "").strip()
        if not event or is_non_news_topic(event):
            dropped += 1
            continue
        kept_items.append(_apply_event(item, event, reason=str(d.get("reason") or "")))

    # Markets not sent to the model (or rest) — keep as-is if not sports.
    for item in rest:
        if is_sports_text(item.label) or is_non_news_topic(item.label):
            dropped += 1
            continue
        kept_items.append(item)

    # Never return an empty pool — if the model is over-aggressive, keep originals.
    if not kept_items:
        say("crystallize: model dropped everything; keeping original shortlist")
        return pool, CrystallizeResult(
            kept=len(items), dropped=0, mode=f"{mode}+safe", estimated_usd=usd,
        )

    # Prefer crystallized GKG/X order; markets after.
    kept_items = _sort_kept(kept_items)
    new_pool = _rebuild_pool(pool, kept_items)
    result = CrystallizeResult(
        kept=len(kept_items), dropped=dropped, mode=mode, estimated_usd=usd,
    )
    say(
        f"crystallize ({mode}): kept {result.kept}, dropped {result.dropped}"
        + (f", ~${usd:.4f}" if usd else "")
    )
    return new_pool, result


# Kinds whose label is a machine artifact rather than something a person published:
# GKG theme codes, actor×action event keys, and bare extracted entity names. A
# ``story`` is excluded — its label comes from a URL slug, which is a real headline in
# all but punctuation — as are ``article``/``news``/``post`` (published headlines) and
# ``market`` (already a discrete, legible question).
_MACHINE_LABEL_KINDS = frozenset({"theme", "event", "person", "organization"})


def _needs_label_repair(item: PoolItem) -> bool:
    """True when the item's label is a machine artifact, not a published headline."""
    return item.kind in _MACHINE_LABEL_KINDS


def _priority_order(items: list[PoolItem]) -> list[PoolItem]:
    """What the model should see first — grain channels before residual tags."""
    rank = {
        "story": 0, "event": 1, "news": 2, "post": 3, "article": 4,
        "market": 5, "theme": 6, "person": 7, "organization": 8,
    }
    ch = {"gkg": 0, "x": 1, "beat": 2, "market": 3}

    def key(i: PoolItem) -> tuple:
        score = 0.0
        try:
            score = float((i.signals or {}).get("score") or 0)
        except (TypeError, ValueError):
            pass
        return (ch.get(i.channel, 9), rank.get(i.kind, 9), -score)

    return sorted(items, key=key)


def _sort_kept(items: list[PoolItem]) -> list[PoolItem]:
    def key(i: PoolItem) -> tuple:
        cryst = 0 if (i.signals or {}).get("crystallized") else 1
        score = 0.0
        try:
            score = float((i.signals or {}).get("score") or 0)
        except (TypeError, ValueError):
            pass
        ch = 0 if i.channel in ("gkg", "x") else 1
        return (cryst, ch, -score)

    return sorted(items, key=key)


def _apply_event(item: PoolItem, event: str, *, reason: str) -> PoolItem:
    """Swap the machine label for the event sentence, keeping the original for audit.

    Evidence is left strictly alone. This used to write the generated sentence over
    ``evidence[0].title``, which put model prose where a source's own words had been —
    in the artifact we persist, indistinguishable from the real thing. Nothing needed
    it (synthesis reads evidence for its URL), and a newsroom that keeps receipts
    cannot have paraphrase impersonating a headline.
    """
    sig = dict(item.signals or {})
    sig["crystallized"] = True
    sig["raw_label"] = item.label[:200]
    if reason:
        sig["crystallize_reason"] = reason[:80]
    return item.model_copy(update={"label": event[:220], "signals": sig})


def _rebuild_pool(old: DiscoveryPool, items: list[PoolItem]) -> DiscoveryPool:
    facets: dict[str, list[str]] = defaultdict(list)
    for item in items:
        for pillar in item.pillars:
            facets[pillar].append(item.id)
    return DiscoveryPool(
        generated_at=old.generated_at,
        gkg_batch_id=old.gkg_batch_id,
        beat_sheet_at=old.beat_sheet_at,
        item_count=len(items),
        by_channel=dict(Counter(i.channel for i in items)),
        by_pillar={p: len(ids) for p, ids in facets.items()},
        facets=dict(facets),
        items=items,
    )


def _llm_decide(
    client: CrystallizeClient,
    items: list[PoolItem],
    say: ProgressFn,
) -> tuple[list[dict[str, Any]], float]:
    payload = [_item_payload(i) for i in items]
    user = (
        "Candidates (JSON). Decide keep/drop and write event sentences for keep=true:\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    say(f"crystallize: sending {len(items)} items to model…")
    decisions = client.complete_json(system=_SYSTEM, user=user)
    usd = float(getattr(client, "last_usd", 0.0) or 0.0)
    if usd:
        try:
            from algent_backend.agent_system.foundation import cost as run_cost
            if run_cost.is_active():
                run_cost.add(usd)
        except Exception:  # noqa: BLE001
            pass
    return decisions, usd


def _item_payload(item: PoolItem) -> dict[str, Any]:
    evidence = ""
    if item.evidence:
        e0 = item.evidence[0]
        evidence = f"{e0.title} | {e0.url}"[:180]
    return {
        "id": item.id,
        "channel": item.channel,
        "kind": item.kind,
        "label": item.label[:200],
        "related": (item.related or [])[:4],
        "evidence": evidence,
        "signals": {
            k: item.signals.get(k)
            for k in ("score", "lane", "rising", "novel", "reasons", "summary")
            if item.signals and k in item.signals
        },
    }


def _heuristic_decide(items: list[PoolItem]) -> list[dict[str, Any]]:
    """Offline / no-key fallback: drop obvious junk; keep labels as-is."""
    out: list[dict[str, Any]] = []
    for item in items:
        label = item.label or ""
        if is_sports_text(label) or is_non_news_topic(label):
            out.append({"id": item.id, "keep": False, "event": None, "reason": "sports/junk"})
            continue
        if item.channel == "market":
            out.append({"id": item.id, "keep": True, "event": label, "reason": "market"})
            continue
        if item.kind in ("story", "news", "post", "article", "event"):
            if _looks_eventful(label) or item.kind == "event":
                out.append({"id": item.id, "keep": True, "event": label, "reason": "heuristic"})
            else:
                out.append({"id": item.id, "keep": False, "event": None, "reason": "weak"})
            continue
        # bare themes/entities — drop under heuristic (need LLM or story path)
        if item.kind in ("theme", "person", "organization"):
            out.append({"id": item.id, "keep": False, "event": None, "reason": "abstract-tag"})
            continue
        out.append({"id": item.id, "keep": True, "event": label, "reason": "default"})
    return out


_EVENTFUL = re.compile(
    r"\b(strike|struck|bomb|missile|sanction|indict|ceasefire|invade|attack|"
    r"arrest|blockade|expel|default|launch|discover|breakthrough|collapse|"
    r"halt|ban|ruling|war|drone|refinery|tanker|hostage|nuclear|talks|"
    r"lawsuit|approves|passes|protests|shooting|budget|bypass|landfall|"
    r"breach|cooperation|conference|intimidat|alleges|weighs|panel)\b",
    re.I,
)


def _looks_eventful(label: str) -> bool:
    if len(label.split()) < 5:
        return False
    return bool(_EVENTFUL.search(label))


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    try:
        n = int(os.environ.get(name, default))
    except ValueError:
        n = default
    return max(lo, min(n, hi))


def _try_openai_client() -> CrystallizeClient | None:
    try:
        from algent_backend.config import get_provider_api_key
        key = get_provider_api_key("openai")
    except Exception:  # noqa: BLE001
        key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    model = os.environ.get(_ENV_MODEL, _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
    return OpenAICrystallizeClient(api_key=key, model=model)


class OpenAICrystallizeClient:
    """Thin OpenAI chat wrapper for crystallize JSON."""

    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self.last_usd = 0.0

    def complete_json(self, *, system: str, user: str) -> list[dict[str, Any]]:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        resp = client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            max_tokens=2500,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": user
                    + "\n\nRespond as JSON object: {\"decisions\":[...]}",
                },
            ],
        )
        usage = resp.usage
        if usage is not None:
            from algent_backend.agent_system.foundation.cost import estimate_model_cost

            self.last_usd = round(
                estimate_model_cost(
                    self.model, usage.prompt_tokens or 0, usage.completion_tokens or 0
                ),
                6,
            )
        text = (resp.choices[0].message.content or "").strip()
        return _parse_decisions(text)


def _parse_decisions(text: str) -> list[dict[str, Any]]:
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("decisions", "items", "results", "candidates"):
            if isinstance(data.get(key), list):
                return data[key]
        # single object?
        if "id" in data:
            return [data]
    return []
