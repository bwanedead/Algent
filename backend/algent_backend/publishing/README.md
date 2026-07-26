# Publishing — finished run → live on ohmega.monster

Articles **auto-publish**: the floors are the gate, not a human. A finished run that earns
`status: publishable` (the caveat reviewer ran and passed) is staged/pushed to the site; anything
that can't earn it goes to a **held queue** you glance at on demand; `blocked` is refused. No one
reads an article before it ships — the grounding floor, figure checks, caveat reviewer, and receipts
are the trust. **Corrections and retractions are the post-publish safety valve, and they are
first-class and visible.**

## The flow

```
rail run ──► site publish <run_id> ──► content/articles/<slug>.md + assets ──► commit to site-live ──► Vercel deploys
                     │                          (+ digest to publish-ledger.md)
                     └─ not publishable ──► backend/publish_held/held-ledger.md   (never blocks)
```

- **Slug = story identity** (`<kebab-title>-<profile-id-hash>`), so a re-run of the same story
  lands on the same slug. Overwriting a live article therefore *requires* `--correction "<reason>"`
  and appends a visible, dated note — never a silent overwrite.
- The **quality digest** (status, caveats, unmatched figures, analytics, per-article cost, run id)
  is the commit message and the `publish-ledger.md` entry — the async monitoring surface.

## One-time setup (operator)

1. **Create the deploy branch** from the branch that has the site code, once, and push it:
   ```
   git branch site-live
   git push -u origin site-live
   ```
2. **Vercel**: import the repo → set **Root Directory = `sites/ohmega-monster`** → set
   **Production Branch = `site-live`** → point `ohmega.monster` at the project. (Framework
   auto-detects as Next.js.) Per-PR/preview deployments get their own origin; production is
   `site-live`.
3. **First `npm run dev` sanity check** — the site-side plumbing (`/feed.xml`, `/sitemap.xml`, the
   OpenGraph/meta tags) is *not exercised by the Python test suite*; it first runs when you do.
   Confirm `/feed.xml` and `/sitemap.xml` respond and an article page shows its OG tags before
   pointing anything (indexers, the future X-poster) at them — a typo in a route file only surfaces
   on that first build.

## Live publish (ON by default)

`ALGENT_SITE_PUBLISH` — **ON by default.** Every eligible finished piece writes into the
`.site-live/` worktree and pushes to `origin/site-live` → Vercel deploys. That is the product
behavior: the rail publishes itself; you do not re-approve each article.

To **pause** shipping without code changes: set `ALGENT_SITE_PUBLISH=0` (or `false` / `off`).
Then runs still stage into the working-tree site dir but do not push.

## Commands

```
python -m algent_backend.cli site publish --run-id <id>                 # gate + stage/publish
python -m algent_backend.cli site publish --run-id <id> --correction "fixed the rate figure"
python -m algent_backend.cli site publish --run-id <id> --hold-named-individuals   # opt-in safety lane
python -m algent_backend.cli site retract --slug <slug> --reason "source was fabricated"
python -m algent_backend.cli site held                                  # the held-queue ledger
```

- **`--hold-named-individuals`** (optional): holds any piece that pairs a named person with
  accusation-class language for a human glance — where defamation risk concentrates. Coarse and
  conservative; off by default.
- **Retraction** leaves an honest tombstone at the URL (`status: retracted` + reason), never a 404.

## Before flipping the switch: check the gate isn't starving the site

Auto-publish assumes articles actually reach `publishable` at a reasonable rate. Run the rail a few
times and check `site held`: if most pieces are held, the site sits empty. `N held / M published`
is a dial to tune (the caveat lane may be too strict) — deliberately, never by bypassing the gate.

## Branch drift

With humans out of the loop, nobody notices `site-live` lagging your dev branch's **site code**
(CSS/app changes, not content). `site publish` warns when it detects drift; merge dev → `site-live`
to ship code changes. (Auto-published content and assets differ by design and are excluded from the
warning.)

**The branch discipline that keeps this from breaking** — one-way merges, never a hand-written
commit on `site-live`, how to resolve a merge, and how to recover from divergence — is the
[Site Branch Protocol](../../../docs/guides/site-branch-protocol.md). Read it before touching
`site-live` by hand.
