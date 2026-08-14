# Insight — figure-first posts

- Radar is one sentence. Briefing is a roundup + collage. Insight is **a chart (or short GIF) that is the post**.
- Forms are a closed catalog in `analytics_workspace/lib/insight.py`. Do not invent a new matplotlib each time.
- The visual is a claim: numbers come from a named public source. Skip if the search cannot ground a table.
- Standing lenses in `beats.py` are a tie-break, not a fence. Warrant searches first.
- t0/t1 are seeds (`seeds.discovery_brief`), not a whitelist.
- Draw uses the analytics venv + templates (`draw_insight.py`). That is not grok-build. Article `analytics_worker` is the grok-build default (`analytics_harness.DEFAULT_HARNESS = "grok"`).
- Charts carry a faint Ohmega Monster mark + `ohmega.monster` wordmark from `lib/theme.watermark`.
- Critique **fixes** a salvageable picture (title, highlight, form). Abandon a bad premise or an undrawable spec — not an unfamiliar topic.
- Queue: `publishing/insight_queue.py`. Same supervisor as Radar; `newsroom insight start|stop`.
- Motion on X is GIF for now (timeline autoplay). MP4 is a later chunked upload, not this lane's first cut.
- Engagement snapshots: `runs_data/insight_engagement.jsonl` via `publishing/insight_engagement.py`.
