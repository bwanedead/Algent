# newsroom CLI — operator menu presentation (sticky)

## Two menus, never confuse them

| Menu | What it is | Pick / compose with |
|------|------------|---------------------|
| **t0 / pool menu** | Raw discovery leads (wire items). Numbers are pool item indexes. | `--pool-menu`, `--compose N+M` (default path today) |
| **synthesis / vector menu** | Research vectors synthesis built from the pool. Numbers are vector indexes. | `--pick N` on the portfolio — only after synthesis is enabled |

They are **not interchangeable**. A synthesis `#3` is not t0 `#3`.

## When presenting menus in chat (non-negotiable)

- Paste **100% of every numbered line** — never half the list, never “1–10 …”, never “see the log/file”.
- If the run stopped after **t0 only** → paste the **full t0 menu** only.
- If the run included **synthesis** → paste **both** in chat: full **t0 menu** and full **synthesis menu**, clearly labeled.
- Do not truncate titles, labels, `orig:` lines, or theses when pasting for the operator.

## How to run which thing

- **t0 menu (default):** `newsroom run --to menu` — synthesis is **off** unless flipped in-repo.
- **Force pool menu without caring about flags:** `--pool-menu`.
- **t0 + synthesis → vector menu:** set `SYNTHESIS_ENABLED = True` in `agent_system/agents/newsroom/flags.py`, then `newsroom run --to menu`. CLI prints both full menus.

## Operator defaults (not `.env`)

Standing newsroom mode toggles live in **`agent_system/agents/newsroom/flags.py`** — agents edit that file. Do **not** ask the human to set `.env` for synthesis on/off. Optional one-shot only: `ALGENT_SYNTHESIS=0/1` for a single process.
