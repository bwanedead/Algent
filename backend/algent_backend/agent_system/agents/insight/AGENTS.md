# Insight — figure-first posts

- Radar is one sentence. Briefing is a roundup + collage. Insight is **a chart (or short GIF) that is the post**.
- Forms are a closed catalog in `analytics_workspace/lib/insight.py`. Do not invent a new matplotlib each time.
- Ambition lives in `ambition.py` and is composed into contemplate, warrant, and critique.
- Contemplate (`contemplate.py`) picks the question first. Warrant grounds it. t0/t1 are optional climate, not the assignment.
- Standing lenses in `beats.py` are a tie-break, not a fence.
- Draw uses the analytics venv + templates (`draw_insight.py`). That is not grok-build. Article `analytics_worker` is the grok-build default (`analytics_harness.DEFAULT_HARNESS = "grok"`).
- Charts carry a stacked Ohmega Monster mark + wordmark from `lib/theme.watermark`.
- Critique **fixes** a salvageable picture. Abandon a bad premise or an undrawable spec.
- Queue: `publishing/insight_queue.py`. Same supervisor as Radar; `newsroom insight start|stop`.
- Motion on X is GIF for now (timeline autoplay). MP4 is a later chunked upload, not this lane's first cut.
- Engagement snapshots: `runs_data/insight_engagement.jsonl` via `publishing/insight_engagement.py`.
