# Ohmega Monster — the site

An information-first newsroom at **ohmega.monster**. Plain, terminal/wiki feel — the information
is the point, not the polish. Every article carries its **receipts** (sources + how far each claim
could be verified), collapsible at the bottom of the page.

Built with **Next.js (App Router) + TypeScript**, deployed on **Vercel**. Kept minimal now, but the
framework leaves the door open for dynamic features later (search, charts, an app).

## Run locally

```bash
cd site
npm install        # first time only
npm run dev        # http://localhost:3000
```

`npm run build` produces the production build; Vercel runs this on deploy.

## Content model

Articles are plain markdown files in [`content/articles/`](content/articles), one per piece, with
frontmatter:

```markdown
---
title: "…"
dek: "…"          # the standfirst
date: "2026-06-29"
status: "publishable"   # honest status from the pipeline; shown to the reader
---

<the prose>

## How we know this — sources & verification
<the receipts appendix — rendered as a collapsible section>
```

The `## How we know this` heading is the split point: everything above is the article, everything
from it down becomes the collapsible receipts. Nothing else about the file is special — publishing
is just *writing a markdown file here*.

## The publish flow (git-driven)

```
editorial_pipeline produces article_published.md + report
   → HUMAN APPROVAL (reads the status + receipts; approves publishable pieces)
   → the approved piece is written here as content/articles/<slug>.md
   → commit + push  →  Vercel auto-builds & deploys  →  live on ohmega.monster
```

The backend→site converter (produced article → frontmatter'd markdown here) is the next piece to
build. Recommended: publish from a dedicated branch (e.g. `publish`) that Vercel is pointed at, so
`main` stays for development and the live site only moves when an approved article is pushed.

## Deploy (Vercel)

1. Import this repo into Vercel; set the **Root Directory** to `site/`.
2. Framework preset: **Next.js** (auto-detected). Build command / output are the defaults.
3. Point the production deployment at your publish branch, and add the domain `ohmega.monster`.
