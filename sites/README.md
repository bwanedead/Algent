# sites/

Front-ends for Algent's projects. Algent is an agentic hub/universe, so this holds many sites
over time — each self-contained, with its own stack, dependencies, and deploy target.

- [`ohmega-monster/`](ohmega-monster) — the newsroom (**ohmega.monster**). The first, and the one
  the editorial pipeline publishes to. Next.js on Vercel.

Each site is independent: `cd sites/<name>` and follow its own README. Nothing here shares a
build or a dependency tree with the Python backend (`backend/`) — the backend *produces* content
(articles, and later more), these sites *present* it.
