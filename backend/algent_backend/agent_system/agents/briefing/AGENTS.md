# Briefing lane

Themed roundups from the **t1 synthesis menu**, posted to X. Not Radar (one looked-up fact) and not an article.

- Source of truth is a frozen `research_portfolio.json`. Radar overlap is allowed — a roundup may re-express something Radar already said.
- Image: a wordless collage via `generate_hero_image`. **Never pass a headline, thesis, or number as the image subject** — same Florida-chart failure as heroes. Pillar → a short physical scene, then the existing subject guards.
- Stamp is the first line: `today's headlines on {topic}:` — no `Radar:` prefix.
- Queue lives at `runs_data/briefing_queue.jsonl`. The radar supervisor ticks this lane; do not start a second daemon.
