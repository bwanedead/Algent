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

## Operator defaults (not `.env`)

`agent_system/agents/newsroom/flags.py`: `SYNTHESIS_ENABLED`, `SYNTHESIS_TARGET_VECTORS`. Agents edit that file — not `.env`.
