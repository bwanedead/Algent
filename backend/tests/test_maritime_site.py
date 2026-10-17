"""The site reads what the backend writes (checked by inspection of the TypeScript: there is no node here)."""

from __future__ import annotations

import re
from pathlib import Path

from algent_backend.maritime import publish
from algent_backend.maritime.contracts import KINDS

SITE = Path(__file__).resolve().parents[2] / "sites" / "ohmega-monster"


def _site(*parts: str) -> str:
    return (SITE / Path(*parts)).read_text(encoding="utf-8")


def test_the_site_type_carries_every_published_column_and_the_kinds_match():
    ts = _site("lib", "maritime-shared.ts")
    body = ts.split("export type MaritimeEvent = {", 1)[1].split("\n};", 1)[0]
    assert set(publish._COLUMNS) <= set(re.findall(r"^\s+(\w+):", body, re.M))
    assert set(re.findall(r'"(\w+)"', ts.split("export type MaritimeKind =", 1)[1].split(";", 1)[0])) == set(KINDS)
    labels = ts.split("KIND_LABEL: Record<MaritimeKind, string> = {", 1)[1].split("};", 1)[0]
    assert set(re.findall(r"^\s+(\w+): ", labels, re.M)) == set(KINDS)


def test_the_agent_surface_the_layer_the_page_and_the_vessel_history_exist_and_the_layer_is_off_by_default():
    assert 'path: "/maritime"' in _site("lib", "api", "router.ts") and 'name: "get_maritime_behaviour"' in _site("lib", "api", "mcp-tools.ts")
    assert '"maritime_events"' in _site("lib", "maritime.ts") and "maritimeOp" in _site("lib", "api", "ops-maritime.ts")
    live = _site("components", "live", "LiveWorldMap.tsx")
    assert 'new Set(["coverage", "shadow"])' in live and "ohmega-live-off-v3" in live and "shadowLayers" in live
    assert 'shadow: ["shadow", "shadow-track"]' in _site("components", "live", "liveLayers.ts")
    assert "BehaviourList" in _site("app", "intel", "places", "[id]", "page.tsx") and "/intel/maritime" in _site("app", "sitemap.ts")
    assert "marks: 3.1" in _site("components", "map", "mapLayers.ts")


def test_existing_layers_keep_their_paint():
    """The /live map look is sacred: the new layer is additive. The earlier kinds' draw order values are unchanged."""
    order = re.search(r"const ORDER: Record<LayerKind, number> = \{(.*?)\};", _site("components", "map", "mapLayers.ts"), re.S).group(1)
    for kind, value in (("area", "0"), ("heat", "1"), ("line", "2"), ("rings", "2.5"), ("dots", "3"), ("assets", "3.2"), ("icons", "3.5"), ("numbered", "4")):
        assert f"{kind}: {value}" in order


def test_client_components_never_import_the_server_only_reads():
    root = SITE / "components"
    files = [*root.joinpath("maritime").glob("*.tsx"), root / "live" / "LiveWorldMap.tsx", root / "live" / "shadowLayers.ts"]
    assert files
    for f in files:
        assert 'from "@/lib/maritime"' not in f.read_text(encoding="utf-8"), f.name
