# Site Branch Protocol — how code and articles reach ohmega.monster

The one durable rule for the live site's git, written down so we never re-create the mess
that produced add/add merge conflicts on files nobody edited twice.

**The rule, in one sentence:** all code work happens on `organic-dev` and flows *one direction*
into `site-live`; `site-live` never receives a hand-written commit.

---

## The two branches

| Branch | Role | What may land on it |
|---|---|---|
| **`organic-dev`** | The dev branch. All human/agent code work. | Every code commit, doc, test — everything. |
| **`site-live`** | Production. Vercel deploys `origin/site-live`. | **Only** two things (below). Never a hand-written commit. |

Vercel is configured: Root Directory `sites/ohmega-monster`, Production Branch `site-live`. A
push to `origin/site-live` is a production deploy. Nothing else deploys.

## The only two things that may land on `site-live`

1. **A merge *from* `organic-dev`** — this is how site *code* (the Next.js app, styling,
   converter, lib) reaches production. Always a merge, always in this direction.
2. **An auto-publish commit from the rail** — content + assets + `publish-ledger.md`, written by
   the pipeline into the `.site-live/` worktree and pushed. This is the only writer of
   `sites/ohmega-monster/content/articles/` and `public/analytics/` on `site-live`.

If you find yourself about to `git commit` while checked out on `site-live`, or to cherry-pick a
code change onto it, **stop** — that is exactly the move that broke it before.

## Why the rule exists (the failure we already hit)

The redesign was committed to **both** branches separately — same change, two different SHAs
(`be7db59` on `organic-dev`, `09820ba` on `site-live`, both "Simplify newsroom display"). Git then
saw two unrelated histories touching the same lines and raised **add/add conflicts** on files
neither branch had legitimately diverged on. That is what duplicate lineage produces. One-way
merges make it impossible: `site-live` only ever *contains* `organic-dev`'s history, never a
parallel copy of it.

## Routine: shipping site code to production

When you've changed the site's code on `organic-dev` (styling, the article page, `lib/`, the
converter output shape) and want it live, merge dev → live via the worktree so your main checkout
is never disturbed:

```bash
# from repo root, main checkout stays on organic-dev
git -C .site-live fetch origin
git -C .site-live merge origin/organic-dev        # or: git -C .site-live merge organic-dev
```

**Resolving conflicts — the one careful part.** Conflicts should only ever be in **code** files
(`app/`, `lib/`, `components/`, CSS). For those, `organic-dev` is authoritative (it has the newest
code *and* whatever live already had), so take its side:

```bash
git -C .site-live checkout --theirs <conflicted code file>   # 'theirs' = the branch being merged in (organic-dev)
git -C .site-live add <that file>
```

**Never** resolve a conflict inside `content/articles/` or `public/analytics/` by taking
`organic-dev`'s tree — those exist *only* on `site-live` (the rail writes them there). If a content
path ever conflicts, keep `site-live`'s version (`--ours`). In practice content never conflicts,
because `organic-dev` doesn't write it.

Then finish and deploy:

```bash
git -C .site-live diff --name-only --diff-filter=U   # must be empty (no markers left)
grep -rn '<<<<<<<' .site-live/sites/ohmega-monster/   # sanity: no leftover markers
git -C .site-live commit --no-edit
git -C .site-live push origin site-live               # this is the deploy
```

## The drift warning tells you when a merge is due

`site publish` (and the rail's publish step) print a **drift warning** whenever `site-live` is
behind `organic-dev` on *site code* (content and analytics paths are excluded — they differ by
design). When you see it, that's the cue to run the routine above. It's a two-dot tree comparison,
so it only fires on genuine drift, not on the duplicate-lineage phantom that started all this.

## The `.site-live/` worktree

`.site-live/` (repo root, gitignored) is a dedicated git worktree checked out to `site-live`. The
rail's auto-publish writes and pushes through it so the operator's main working tree is never
touched mid-run. It's created on demand; if it's missing, the publish step recreates it. You can
operate on it directly with `git -C .site-live ...` as above. Don't delete it mid-publish.

## Auto-publish (live by default)

Live publish is **ON by default**. A rail run that produces an eligible article publishes
itself: write into `.site-live/` and push to `origin/site-live` → Vercel. You do not re-approve
each piece. To **pause** shipping without a code change, set `ALGENT_SITE_PUBLISH=0` (stage only).

Either way, the branch rule holds — the rail is the sanctioned second writer of `site-live`, and
it only ever writes content/assets/ledger, never code.

## If it ever diverges again — recovery

Symptom: `git merge organic-dev` on `site-live` conflicts on code files you didn't touch twice, or
`git log --oneline --graph organic-dev site-live` shows two parallel spines with duplicate commit
messages.

Fix: merge (don't rebase, don't force-push) so the lineages fuse — resolve code conflicts toward
`organic-dev`, preserve `site-live`'s `content/`, commit, push. After one clean merge, `site-live`
contains `organic-dev`'s history and the divergence is gone. **Do not** `git reset --hard` or
force-push `site-live` to "clean it up" — that can orphan published articles that live only there.

## The short version (print this on your wall)

- Code → `organic-dev` only.
- `site-live` gets **merges from dev** and **rail auto-publishes** — nothing else, ever.
- Merge conflicts are only in code → take `organic-dev`'s side; never touch `content/`.
- Merge, never rebase/force-push `site-live`.
- Drift warning = time to merge dev → live.
