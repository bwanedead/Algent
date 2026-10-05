"""
Pulse display labels — a title that says WHO and WHAT, with the principal actors' flags.

A Pulse is stored as a dimension of a situation ("Relationship deadlock"); on a tile, out of its
situation's context, that name does not say whose relationship. The reader should never have to click to
learn the identity. This cache holds, per Pulse, ``{title, actors_iso2, label_version, built_from}``:

* the TITLE and the principal actors are ONE cheap structured model call per Pulse, made from its
  definition and its situation: who the principal actors are is a semantic judgment, never a scan of names;
* the cache lives OUTSIDE the Pulse store (``intel_store/pulse_labels.json``): a label is display, not
  belief, and nothing here touches how Pulses move;
* it is cached forever and re-made only when the Pulse's definition version differs from the one the label
  was built under (``label_version``) or on an explicit refresh;
* a Pulse with no label falls back to ``"<situation title> · <pulse name>"`` (deterministic): publishing
  never waits for, or fails on, a model.

The harness validates only mechanics: a non-empty title, at most ``MAX_ACTORS`` two-letter codes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .heat import store_dir

SCHEMA = "ohmega.pulse_labels/1"
MAX_ACTORS = 3
MAX_TITLE = 90
SEP = " · "

LABELER_ROLE = """\
You name one dimension that an intelligence desk tracks, so that a reader who sees only its name, with no
page around it, knows WHO it is about and WHAT is measured.

You are given the situation it belongs to and the Pulse's own definition (its name, the question it
answers, what its calm and extreme ends look like).

- `title`: the principal actors first, then the dimension: "US–China · Diplomatic deadlock",
  "Ukraine war · Strike intensity", "Iran proxy axis · Escalation". Name the parties the way a newspaper
  would; use an en dash between two parties. Short (about eight words), plain, no flags or emoji, no
  trailing question. Keep the Pulse's own wording for the dimension when it is already clear.
- `actors_iso2`: the ISO 3166-1 alpha-2 codes of the principal STATE actors the title names ("US" is
  `US`, "UK" is `GB`; the European Union is `EU`), at most three, in the order the title names them.
  Leave it empty when no state or bloc is principal (a global market, a technology race, a non-state
  group on its own); a flag the title does not support is worse than none.
"""


class LabelDraft(BaseModel):
    title: str = Field(description="Who and what: principal actors, then the dimension, e.g. 'US–China · Diplomatic deadlock'.")
    actors_iso2: list[str] = Field(default_factory=list, description="ISO alpha-2 codes of the principal state actors, at most three.")


def path(root: Path | None = None) -> Path:
    return (root or store_dir()) / "pulse_labels.json"


def load(root: Path | None = None) -> dict[str, dict]:
    """Every cached label by Pulse id ({} when there is no cache or it is unreadable)."""
    try:
        data = json.loads(path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    labels = data.get("labels") if isinstance(data, dict) else None
    return {k: v for k, v in (labels or {}).items() if isinstance(v, dict) and str(v.get("title", "")).strip()}


def _save(labels: dict[str, dict], root: Path | None = None) -> None:
    target = path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"schema": SCHEMA, "labels": dict(sorted(labels.items()))}, ensure_ascii=False,
                                 indent=2) + "\n", encoding="utf-8", newline="\n")


def fallback_title(situation_title: str, pulse_name: str) -> str:
    """The deterministic title a Pulse without a label shows."""
    return SEP.join(p for p in (situation_title.strip(), pulse_name.strip()) if p)


def display(labels: dict[str, dict], pulse_id: str, situation_title: str, pulse_name: str) -> dict[str, Any]:
    """``{title, actors_iso2}`` for a Pulse: its cached label (even a stale one: better than none), else the fallback."""
    label = labels.get(pulse_id)
    if label:
        return {"title": str(label["title"]), "actors_iso2": [c for c in label.get("actors_iso2") or [] if isinstance(c, str)]}
    return {"title": fallback_title(situation_title, pulse_name), "actors_iso2": []}


def _clean(draft: LabelDraft) -> tuple[str, list[str]]:
    title = " ".join(draft.title.split())[:MAX_TITLE].rstrip(" ·-–,;:")
    codes: list[str] = []
    for raw in draft.actors_iso2:
        code = raw.strip().upper()
        code = "GB" if code == "UK" else code
        if re.fullmatch(r"[A-Z]{2}", code) and code not in codes:
            codes.append(code)
    return title, codes[:MAX_ACTORS]


def _ask(context: Any, config: Any, model_spec: Any, situation: Any, pulse: Any) -> LabelDraft | None:
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    d = pulse.definition
    task = (f"SITUATION: {situation.title}\n{situation.summary}\nEntities it covers: {', '.join(situation.entities) or '-'}\n\n"
            f"PULSE NAME: {pulse.name}\nQUESTION: {d.question}\nCALM END: {d.low_end or '-'}\nEXTREME END: {d.high_end or '-'}\n\n"
            "TASK: name this Pulse.")
    model = context.model_resolver.resolve(model_spec).client.with_structured_output(LabelDraft)
    out = model.invoke([SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, LABELER_ROLE)),
                        HumanMessage(content=task)], config=config)
    return out if isinstance(out, LabelDraft) else None


def build_missing(context: Any, store: Any, *, model_spec: Any, refresh: bool = False, root: Path | None = None,
                  config: Any = None) -> dict[str, Any]:
    """Label every Pulse (in an active situation) that has no label, or whose label was made under another
    definition version (``refresh``: all of them). One model call per Pulse that needs one, none for the
    rest; one failure never stops the others. Returns ``{built, reused, failed:[{pulse, error}]}``."""
    labels, report = load(root), {"built": [], "reused": 0, "failed": []}
    situations = {s.id: s for s in store.situations() if s.status == "active"}
    for pulse in store.pulses():
        sit = situations.get(pulse.situation_id)
        if sit is None:
            continue
        version = pulse.definition.version
        have = labels.get(pulse.id)
        if have and not refresh and have.get("label_version") == version:
            report["reused"] += 1
            continue
        try:
            draft = _ask(context, config, model_spec, sit, pulse)
            title, codes = _clean(draft) if draft else ("", [])
        except Exception as exc:  # noqa: BLE001 - one Pulse's label must never stop the rest
            report["failed"].append({"pulse": pulse.id, "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
            continue
        if not title:
            report["failed"].append({"pulse": pulse.id, "error": "no usable title"})
            continue
        labels[pulse.id] = {"title": title, "actors_iso2": codes, "label_version": version,
                            "built_from": fallback_title(sit.title, pulse.name)}
        _save(labels, root)                      # after each: an interrupted run keeps what it paid for
        report["built"].append(pulse.id)
    return report
