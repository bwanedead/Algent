# The intelligence desk: board, novelty, lifecycle, focus

Vision: `docs/vision/ohmega-intelligence-engine.md` ("The intelligence desk", "Depth: from dashboard to model").
Code: `backend/algent_backend/agent_system/agents/intel/` (`base.py`, `heat.py`, `novelty.py`, `focus.py`, `daily.py`).

The desk's focus follows the world: a theater enters when something new happens, leaves when nothing has for about
a week, and detection draws on a base wider than our own radar.

## The board (`heat.run`, `newsroom intel heat`)

1. **Base** (`base.assemble`): the window's headlines from three tagged source classes — `radar` (our editions),
   `wikipedia` (Current Events: cited events that happened) and `library` (titles of recent documents in our
   crawled trusted-source index). A class that fails to load is absent. Near-identical titles inside a class
   (same content words) are dropped; the rest is cut to `CLUSTER_LINE_BUDGET` lines by water-filling (equal share
   per class, surplus to the others), spread over days and over each class's groups.
2. **Cluster**: one model call groups the lines into theaters, reusing registry ids (identity continuity).
3. **Heat** (`heat.measure`): per class and window, share = theater members / headlines of that class (the
   *shown* lines are the denominator). A window's share is the mean over classes that have data; a class with no
   headlines is absent, never zero. Trend (heating/cooling/steady/new) compares the mean share change with the
   standard error of that mean. Heat = 100 x (w x recent + 0.25 x earlier). `by_class` on each heat row shows the parts.
4. **Novelty** (`novelty.measure`, mechanical): per theater, items dated after its last daily section — new member
   headlines by class, statements on record that `sensing` ties to it, matched series newly outside their range
   (unusual now, not as of the last section). Record: `heat[].novelty = {since, headlines{class}, statements,
   instruments, total, newest}`.
5. **Lifecycle** (`focus.classify`): `last_novel` = newest dated thing seen (only moves forward; persisted in
   `theaters.json` with `state`). `quiet` when older than `FOCUS_DROP_DAYS = 7` (the operator's rule, 10-04);
   `new` when first seen in the window and never in a daily; otherwise `active`. Novelty returning makes it
   active again on the next board. Registry theaters absent from a board are listed in `board.lifecycle`.

## Focus (`focus.plan`, used by `daily.produce_daily`)

- In focus: `new`/`active` theaters with novelty > 0, ranked by heat x novelty total. `--top` is a ceiling.
- `watch` (daily record): live theaters not written up — `nothing_new` or `over_budget` — with a one-line note.
- `quiet` (daily record): once-covered theaters that went quiet, with last change date and countries.
- Boards without lifecycle data fall back to the old top-by-heat and empty `watch`/`quiet`.
- A theater in focus whose novelty is zero-ish gets a `NEW SINCE` line in the section task; the daily doctrine
  says an unchanged section is short and says so.

## Site

`/geopolitics` daily: "Also watching" and "Quiet" after the sections (`DailyWatching.tsx`); `/intel/theaters`
rows show the lifecycle state (from the dossier index `state`/`last_novel`).
