"""Debug why ICE v2 was not demoted on rail 0022."""
from __future__ import annotations

from algent_backend.agent_system.agents.routing.contracts import (
    RankedChoice,
    RouteCandidate,
    RouteRanking,
)
from algent_backend.agent_system.agents.routing.cooldown import (
    anchors,
    cooled_by,
    demote_cooled,
    significant_tokens,
)
from algent_backend.publishing import site_git
from algent_backend.publishing.history import recent_headlines

prior = (
    "ICE's FY2026 data show a June surge in arrests and higher detention, "
    'but "criminals first" doesn\'t match the custody mix'
)
prior_curly = (
    "ICE\u2019s FY2026 data show a June surge in arrests and higher detention, "
    "but \u201ccriminals first\u201d doesn\u2019t match the custody mix"
)
blob = (
    "ICE arrest surge and record detention levels under renewed interior-enforcement push "
    "U.S. immigration enforcement is accelerating sharply, with record arrest levels, more detention, "
    "and a growing share of detainees without criminal convictions, making the operational reality "
    "and legal backlash central to the deportation agenda."
)

print("=== Token diagnostics ===")
print("blob tokens:", sorted(significant_tokens(blob)))
print("prior tokens:", sorted(significant_tokens(prior_curly)))
print("shared anchors:", sorted(anchors(blob) & anchors(prior_curly)))
print("shared tokens:", sorted(significant_tokens(blob) & significant_tokens(prior_curly)))
print("'ice' in either?", "ice" in significant_tokens(blob), "ice" in significant_tokens(prior_curly))
print("cooled ascii:", cooled_by(blob, [prior]))
print("cooled curly:", cooled_by(blob, [prior_curly]))

print("\n=== Live recent_headlines (as promotion sees) ===")
root = site_git.repo_root()
dirs = [site_git.live_site_dir(root), site_git.site_dir(root)]
print("dirs:", dirs)
recent = recent_headlines(dirs)
for when, title in recent[:8]:
    print(when[:10], title[:100])

# Exclude the just-published mid-2026 piece to simulate pre-0022 state
titles_pre = [t for _, t in recent if "mid-2026" not in t.lower()]
print("\n=== demote_cooled simulation (pre-0022 titles) ===")
candidates = [
    RouteCandidate(
        id="v2",
        label="ICE arrest surge and record detention levels under renewed interior-enforcement push",
        summary=blob.split("push ", 1)[-1] if "push " in blob else blob,
    ),
    RouteCandidate(
        id="v1",
        label="Google hit with €890M EU antitrust fine over search and Play self-preferencing",
        summary="EU antitrust fine for self-preferencing",
    ),
    RouteCandidate(
        id="v5",
        label="Applied Intuition launches Dana, an agentic platform for physical AI",
        summary="physical AI product launch",
    ),
]
ranking = RouteRanking(
    choices=[
        RankedChoice(candidate_id="v2", rank=1, score=92, rationale="ICE scale"),
        RankedChoice(candidate_id="v1", rank=2, score=89, rationale="Google fine"),
        RankedChoice(candidate_id="v5", rank=3, score=84, rationale="AI"),
    ],
    note="LLM claimed demotion",
)
recent_tuples = tuple((f"2026-07-22", t) for t in titles_pre[:15])
# force include known prior
if not any("FY2026" in t or "fy2026" in t.lower() for t in titles_pre):
    recent_tuples = (("2026-07-22", prior_curly),) + recent_tuples

out = demote_cooled(ranking, candidates, recent_tuples)
print("top after demote:", out.choices[0].candidate_id, out.choices[0].rank)
print("order:", [c.candidate_id for c in out.choices])
print("note:", out.note[:400])

print("\n=== cooled_by each candidate vs pre titles ===")
for c in candidates:
    cool, why = cooled_by(f"{c.label} {c.summary}", [t for _, t in recent_tuples])
    print(c.id, cool, why[:120] if why else "")
