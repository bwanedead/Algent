import json
from pathlib import Path

from algent_backend.agent_system.agents.routing.cooldown import anchors, cooled_by
from algent_backend.publishing import site_git
from algent_backend.publishing.history import recent_headlines

port = json.loads(
    Path(
        "runs_data/discovery_synthesis/0008__8892969b-484f-49ff-9e7d-c55e86e04d7e/"
        "artifacts/research_portfolio.json"
    ).read_text(encoding="utf-8")
)
titles = [
    t
    for _, t in recent_headlines(
        [site_git.live_site_dir(site_git.repo_root()), site_git.site_dir(site_git.repo_root())]
    )
]
for vid in ("v01", "v02", "v05", "v23", "v03", "v22", "v07", "v21"):
    v = next(x for x in port["vectors"] if x["id"] == vid)
    blob = f"{v['title']} {v['thesis']} {v['rationale']}"
    print(vid, "title:", v["title"][:70])
    print("  anchors sample:", sorted(anchors(blob))[:25])
    cool, why = cooled_by(blob, titles)
    print("  cooled?", cool, why[:120] if why else "")
