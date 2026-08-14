# Insight — figure-first posts

- Radar is one sentence. Briefing is a roundup + collage. Insight is **a chart (or short GIF) that is the post**.
- Forms are a closed catalog in `analytics_workspace/lib/insight.py`. Do not invent a new matplotlib each time.
- The visual is a claim: numbers come from a named public source. Skip if the search cannot ground a table.
- Critique **fixes** a salvageable picture (title, highlight, form). Abandon if the premise is bad **or** the spec cannot be drawn (no source URL, too few rows).
- Queue: `publishing/insight_queue.py`. Same supervisor as Radar; `newsroom insight start|stop`.
- Motion on X is GIF for now (timeline autoplay). MP4 is a later chunked upload, not this lane's first cut.
- Engagement snapshots: `runs_data/insight_engagement.jsonl` via `publishing/insight_engagement.py`.
