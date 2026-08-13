# newsroom CLI — operator menu presentation (sticky)

## Two menus, never confuse them

| Menu | What it is | Pick / compose with |
|------|------------|---------------------|
| **t0 / pool menu** | Raw discovery leads (wire items). Numbers are pool item indexes. | `--pool-menu`, `--compose N+M` |
| **synthesis / vector menu** | Research vectors synthesis built from the pool. Numbers are vector indexes. | `--pick N` (+ optional `--menu PATH` to pin a frozen portfolio) |

They are **not interchangeable**. A synthesis `#3` is not t0 `#3`.

## Promotion paths (menu is optional)

| Path | Command | When |
|------|---------|------|
| Live / pinned menu pick | `--from menu --pick 14` or `--menu <portfolio.json\|run-dir> --pick 14` | Numbers from a menu you were shown — **pin with `--menu`** so a later rebuild cannot renumber them |
| Ad-hoc brief | `--brief "Title" --angle "thesis…"` | Invented topic, or revive a stale story by content — **no menu id** |
| Compose from t0 | `--compose 88+114 --angle "…"` | Hand-group raw pool items |

Do **not** remake synthesis just to re-pick. Freeze the portfolio path (or use `--brief`) and launch.

## When presenting menus in chat (non-negotiable)

- Paste **100% of every numbered line** — never half the list, never “1–10 …”, never “see the log/file”.
- If the run stopped after **t0 only** → paste the **full t0 menu** only.
- If the run included **synthesis** → paste **both** in chat: full **t0 menu** and full **synthesis menu**, clearly labeled.
- Do not truncate titles, labels, `orig:` lines, or theses when pasting for the operator.

## How to run which thing

- **t0 + synthesis → vector menu (default):** `newsroom run --to menu` — soft size `SYNTHESIS_TARGET_VECTORS` in `flags.py`.
- **t0 pool menu only:** `--pool-menu`, or `SYNTHESIS_ENABLED = False`.
- **Pinned picks:** `newsroom run --from menu --menu runs_data/discovery_synthesis/<run> --pick 1,2,14`.
- **Resume a failed rail:** `newsroom resume` (newest unfinished) or `--run <id|dir>`. Assesses artifacts and continues from the next unpaid stage **in the same run** — does not re-buy a draft, profile, or figure that is already on disk. `--from editorial` (etc.) forces a redo from that stage. `--dry-run` prints the plan. Shipping always goes through the rail (skipped stages stay skipped).
- **Radar on/off:** `newsroom radar start` / `newsroom radar stop` — one background supervisor (discovery + Radar posts). Closing the laptop ends it; the queue stays on disk.
- **Briefing on/off:** `newsroom briefing start` / `newsroom briefing stop` — same supervisor, not a second process. Stop pauses only the roundup lane.

These three `--from` flags are **not** the same contract:

| Command | Run | What `--from` means |
|---------|-----|---------------------|
| `newsroom resume --from editorial` | **same** run | redo editorial; reuse profile/gauntlet already on disk |
| `newsroom run --from editorial` | **new** run | CLI ladder slice (t0/synthesis/menu only); the rail still runs in full once handed a portfolio |
| `runs start --from-run <id>` | **new** run | reuse that run's t1 portfolio only; routing onward (cooldown still applies) |

## Operator defaults (not `.env`)

`agent_system/agents/newsroom/flags.py`: `SYNTHESIS_ENABLED`, `SYNTHESIS_TARGET_VECTORS`, and
`synthesis_max_output_tokens()` (scales with the target so large portfolios are not truncated
into empty `vectors`). Agents edit that file — not `.env`.

## Single-flight (do not overlap rails)

`newsroom run` takes an exclusive lock at `runs_data/newsroom_run.lock` whenever it might spend
(synthesis or a rail). A second launch while another is alive exits with a busy error. If you
must stop a run, use `python -m algent_backend.cli runs stop --run-id …` (tree-kill) — do not
only kill the parent shell and relaunch. Overlapping rails double-spend and false-trip analytics
escapes.
