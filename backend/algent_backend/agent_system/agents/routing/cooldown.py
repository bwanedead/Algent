"""
Cooldown — agent-semantic only.

Recent published headlines are loaded for the routing (and synthesis) agent
payload. The model flags same-story-family matches. There is **no** lexical /
token-overlap demotion floor.

History lives in ``publishing.history.recent_headlines``. Promotion attaches
that list to ``RoutingBrief.recent``; see ``promotion.rank_portfolio``.
"""
