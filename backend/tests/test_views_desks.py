"""The views' desk table is the site's (lib/desks.ts) and the backend registry's (agents/intel/domains.py): one list, three readers. Pure text comparison, no node."""

from __future__ import annotations

import re
from pathlib import Path

from algent_backend.views import flags

REPO = Path(__file__).resolve().parents[2]
DESKS_TS = REPO / "sites" / "ohmega-monster" / "lib" / "desks.ts"


def test_the_view_desks_match_the_sites_desk_list():
    src = DESKS_TS.read_text(encoding="utf-8")
    block = src[src.index("export const DESKS"): src.index("/** \"twice a day")]
    ids = re.findall(r'^\s+id: "(\w+)",', block, re.M)
    domains = [tuple(re.findall(r'"(\w+)"', m)) for m in re.findall(r"^\s+domains: \[([^\]]*)\]", block, re.M)]
    catch = [bool(re.search(r"catchAll: true", chunk)) for chunk in re.split(r"^\s+\{\s*$", block, flags=re.M)[1:]]
    assert ids == [d["id"] for d in flags.DESKS]
    assert domains == [tuple(d["domains"]) for d in flags.DESKS]
    assert catch == [d["catch_all"] for d in flags.DESKS]


def test_every_registered_domain_with_a_daily_is_a_view_desk():
    from algent_backend.agent_system.agents.intel import domains

    registered = {d.id for d in domains.REGISTRY.values()} if isinstance(domains.REGISTRY, dict) else {d.id for d in domains.REGISTRY}
    assert {d["id"] for d in flags.DESKS} <= registered
