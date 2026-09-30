"""
``newsroom pulse`` — Ohmega Pulse: seed, review, commit, inspect.

    newsroom pulse seed                    # DRY RUN: propose situations + Pulses, write a review
    newsroom pulse seed --only sit_ukraine_war
    newsroom pulse commit <seed dir>       # persist exactly what was reviewed (no model re-run)
    newsroom pulse show                    # every Pulse: position, band, velocity, freshness
    newsroom pulse log <pulse_id>          # its full influence history

Seeding never writes to the store: it saves ``seed.json`` + ``review.md`` under
``runs_data/pulse_seed/<stamp>/``. Commit reads that file, so what gets stored is what a human
read. See docs/architecture/pulse-system.md.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("pulse", help="Ohmega Pulse: seed / commit / show / log")
    verbs = p.add_subparsers(dest="pulse_verb", required=True)
    s = verbs.add_parser("seed", help="propose the seed situations and Pulses (dry run)")
    s.add_argument("--only", default="", help="seed just this situation id")
    c = verbs.add_parser("commit", help="persist a reviewed seed proposal")
    c.add_argument("seed_dir", help="runs_data/pulse_seed/<stamp> (or its seed.json)")
    r = verbs.add_parser("reassess", help="weekly anchored + blind reassessment")
    r.add_argument("--pulse", default="", help="just this pulse id")
    verbs.add_parser("show", help="every Pulse's current reading")
    lg = verbs.add_parser("log", help="one Pulse's influence history")
    lg.add_argument("pulse_id")
    p.set_defaults(handler=run_pulse)


def run_pulse(args: Any) -> int:
    return {"seed": _seed, "commit": _commit, "reassess": _reassess, "show": _show,
            "log": _log}[args.pulse_verb](args)


def _seed(args: Any) -> int:
    from algent_backend.agent_system.agents.pulse import seed as sd
    from algent_backend.agent_system.agents.pulse.catalog import SEED_SITUATIONS
    from algent_backend.agent_system.agents.research.store import JsonProfileStore
    from algent_backend.agent_system.foundation.models import ModelResolver, house_spec
    from algent_backend.agent_system.runs.context import AgentRunContext
    from algent_backend.agent_system.runs.control_plane.layout import runs_data_root

    store = JsonProfileStore()
    profiles = [p.model_dump() for p in (store.get(i) for i in store.list_ids()) if p is not None]
    situations = tuple(s for s in SEED_SITUATIONS if not args.only or s.id == args.only)
    if not situations:
        print(json.dumps({"error": f"no seed situation {args.only!r}"}))
        return 2
    ctx = AgentRunContext(run_id="pulse-seed", model_resolver=ModelResolver())
    links = sd.attach(ctx, None, profiles, situations=situations,
                      model_spec=house_spec(reasoning_effort="low", temperature=0.1))
    by_id = {p["id"]: p for p in profiles}
    judge = house_spec(reasoning_effort="medium", temperature=0.2, max_tokens=16384)
    seeded = [sd.seed_situation(ctx, None, s, [by_id[i] for i in links.get(s.id, [])], model_spec=judge)
              for s in situations]

    out = Path(runs_data_root()) / "pulse_seed" / datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "seed.json").write_text(json.dumps(
        [{"situation_id": x.situation.id, "profile_ids": x.profile_ids, "problems": x.problems,
          "draft": x.draft.model_dump()} for x in seeded], ensure_ascii=False, indent=2), encoding="utf-8")
    titles = {p["id"]: str(p.get("title") or p["id"]) for p in profiles}
    (out / "review.md").write_text(sd.render_review(seeded, titles), encoding="utf-8")
    print(json.dumps({
        "seed_dir": str(out), "review": str(out / "review.md"),
        "situations": {x.situation.id: {"profiles": len(x.profile_ids),
                                        "pulses": len(x.draft.pulses),
                                        "assessed": sum(p.position is not None for p in x.draft.pulses),
                                        "corrections": len(x.problems)} for x in seeded},
        "note": "nothing stored — read review.md, then `newsroom pulse commit <seed_dir>`",
    }, indent=2))
    return 0


def _commit(args: Any) -> int:
    from algent_backend.agent_system.agents.pulse import PulseStore
    from algent_backend.agent_system.agents.pulse import seed as sd
    from algent_backend.agent_system.agents.pulse.catalog import SEED_SITUATIONS

    path = Path(args.seed_dir)
    path = path if path.suffix == ".json" else path / "seed.json"
    catalog = {s.id: s for s in SEED_SITUATIONS}
    seeded = [sd.SeededSituation(situation=catalog[r["situation_id"]], profile_ids=r["profile_ids"],
                                 problems=r["problems"], draft=sd.SituationDraft.model_validate(r["draft"]))
              for r in json.loads(path.read_text(encoding="utf-8"))]
    made = sd.commit(PulseStore(), seeded, run_id=f"seed_{path.parent.name}")
    print(json.dumps({"committed_pulses": made, "from": str(path)}, indent=2))
    return 0


def _reassess(args: Any) -> int:
    from algent_backend.agent_system.agents.pulse import PulseStore
    from algent_backend.agent_system.agents.pulse.reassess import reassess_all
    from algent_backend.agent_system.foundation.models import ModelResolver, house_spec
    from algent_backend.agent_system.runs.context import AgentRunContext

    ctx = AgentRunContext(run_id="pulse-reassess", model_resolver=ModelResolver())
    out = reassess_all(ctx, None, PulseStore(), only=args.pulse,
                       model_spec=house_spec(reasoning_effort="medium", temperature=0.2, max_tokens=16384))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def _show(args: Any) -> int:
    from algent_backend.agent_system.agents.pulse import PulseStore

    from algent_backend.agent_system.agents.pulse.freshness import unprocessed

    store = PulseStore()
    rows = []
    for sit in store.situations():
        stale = len(unprocessed(store, sit.id))
        for pulse in store.pulses(sit.id):
            st = store.state(pulse.id)
            rows.append({"situation": sit.title, "pulse": pulse.name, "id": pulse.id,
                         "position": st.position, "band": st.band or "unassessed",
                         "v7d": st.velocity_7d, "v30d": st.velocity_30d, "confidence": st.confidence,
                         "evidence_through": st.evidence_through,
                         "reconcile": st.needs_reconciliation, "influences": st.influences,
                         "radar_headlines_since": stale})
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


def _log(args: Any) -> int:
    from algent_backend.agent_system.agents.pulse import PulseStore

    print(json.dumps([i.model_dump() for i in PulseStore().log(args.pulse_id)], indent=2, ensure_ascii=False))
    return 0
