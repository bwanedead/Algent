# newsroom CLI — operator menu presentation (sticky)

## Two menus, never confuse them

| Menu | What it is | Pick / compose with |
|------|------------|---------------------|
| **t0 / pool menu** | Raw discovery leads (wire items). Numbers are pool item indexes. | `--pool-menu`, `--compose N+M`, or `ALGENT_SYNTHESIS=0` |
| **synthesis / vector menu** | Research vectors synthesis built from the pool. Numbers are vector indexes. | `--pick N` on the portfolio |

They are **not interchangeable**. A synthesis `#3` is not t0 `#3`.

## When presenting menus in chat (non-negotiable)

- Paste **100% of every numbered line** — never half the list, never “1–10 …”, never “see the log/file”.
- If the run stopped after **t0 only** → paste the **full t0 menu** only.
- If the run included **synthesis** → paste **both** in chat: full **t0 menu** and full **synthesis menu**, clearly labeled.
- Do not truncate titles, labels, `orig:` lines, or theses when pasting for the operator.

## How to run which thing

- **t0 menu only:** `newsroom run --to menu --pool-menu` (or `--fresh --pool-menu`), **or** set `ALGENT_SYNTHESIS=0` then `--to menu`.
- **t0 + synthesis → vector menu:** `newsroom run --to menu` (default). CLI also prints the t0 menu beside the vector menu.
- Synthesis pause: `ALGENT_SYNTHESIS=0` (durable). Default is **on** if the env var is unset — do not assume it is paused unless you checked.
