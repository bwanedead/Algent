# newsroom CLI — operator menu presentation (sticky)

## Two menus, never confuse them

| Menu | What it is | Pick / compose with |
|------|------------|---------------------|
| **t0 / pool menu** | Raw discovery leads (wire items). Numbers are pool item indexes. | `--pool-menu`, `--compose N+M` |
| **synthesis / vector menu** | Research vectors synthesis built from the pool. Numbers are vector indexes. | `--pick N` on the portfolio |

They are **not interchangeable**. A synthesis `#3` is not t0 `#3`.

## When presenting menus in chat (non-negotiable)

- Paste **100% of every numbered line** — never half the list, never “1–10 …”, never “see the log/file”.
- If the run stopped after **t0 only** → paste the **full t0 menu** only.
- If the run included **synthesis** → paste **both** in chat: full **t0 menu** and full **synthesis menu**, clearly labeled.
- Do not truncate titles, labels, `orig:` lines, or theses when pasting for the operator.

## How to run which thing

- **t0 + synthesis → vector menu (default):** `newsroom run --to menu` — synthesis is **on**; soft target size is `SYNTHESIS_TARGET_VECTORS` in `flags.py`.
- **t0 pool menu only:** `--pool-menu`, or set `SYNTHESIS_ENABLED = False` in `flags.py`.
- **`--pick` works even if synthesis is later turned off** — it reuses the last portfolio; do not force pool numbers.

## Operator defaults (not `.env`)

Standing newsroom mode toggles live in **`agent_system/agents/newsroom/flags.py`**:
- `SYNTHESIS_ENABLED` — run t1 or stop at t0
- `SYNTHESIS_TARGET_VECTORS` — soft aim for portfolio size (currently 40)

Agents edit that file. Do **not** ask the human to set `.env` for these. Optional one-shot only: `ALGENT_SYNTHESIS=0/1`.
