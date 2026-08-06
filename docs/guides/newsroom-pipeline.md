# Running the Newsroom Pipeline — Outcome → Command

**If you want a story made, this is the only page you need.** Everything runs
through one command over a stage ladder. Run from `backend/`, using the project
venv (`.venv\Scripts\python.exe` on Windows).

## The ladder

```text
t0 → synthesis → menu → route → profile → gauntlet → editorial → publish
```

Each stage consumes the one above it, so the only coherent thing to run is a
contiguous range. `--from` and `--to` select that range; both default to the
full ladder.

| stage | what it does |
|-------|--------------|
| `t0` | build the discovery pool from its source channels |
| `synthesis` | pool → t1 research portfolio (headlines → angles) |
| `menu` | print that portfolio as a numbered menu, for picking (stop point) |
| `route` | portfolio → the one promoted vector |
| `profile` | vector → researched t2 signal profile |
| `gauntlet` | review and enrich the profile to maturity |
| `editorial` | profile → drafted, headlined, caveated article |
| `publish` | article → the live site |

## Outcome → command

| I want… | command |
|---------|---------|
| fresh discovery and a menu to pick from | `newsroom run --to menu` |
| **t0 pool only** (pause synthesis; pick by hand) | `ingest t0 --force --menu` or set `ALGENT_SYNTHESIS=0` then `newsroom run --to menu` |
| the menu again, without re-spending on discovery | `newsroom run --from menu --to menu` |
| these menu vectors turned into published articles | `newsroom run --from menu --pick 3,7` |
| the whole thing, unattended | `newsroom run` (needs `ALGENT_SYNTHESIS=1`, the default) |
| an article, but staged rather than shipped | `newsroom run --to editorial` |
| to see what would run, spending nothing | add `--dry-run` |
| discovery from only some channels | `newsroom run --to menu --channels gkg,science` |
| a different figure-drawing harness | add `--analytics-harness grok` |
| the raw t0 item menu, to blend items myself | `newsroom run --to menu --pool-menu` |
| these raw t0 items blended into one article | `newsroom run --compose 88+114 --angle "…"` |

**Synthesis pause.** `ALGENT_SYNTHESIS=0` (also `false`/`off`) skips the t1 synthesis stage so
discovery stops at the raw t0 pool. Use that while you are choosing leads by hand; turn it
back on for scheduled / unattended selection later. `ingest t0` never runs synthesis.

**English menu.** Non-English t0 labels get an English line (`signals.label_en`) with the
original kept underneath — source widely, triage in English. Published articles stay
English-central (drafter doctrine). Pause with `ALGENT_T0_MENU_EN=0` if needed.

```bash
python -m algent_backend.cli newsroom run --to menu
```

```bash
python -m algent_backend.cli newsroom run --from menu --pick 3,7
```

## Picks

The menu is the **t1 portfolio** — research vectors, each an angle with a thesis
and the questions it has to answer. Not the raw t0 pool, which is wire headlines:
picking a headline leaves synthesis free to turn it into a different story, and
picking *"Beyond tech selloff: how China's DUV machine is challenging ASML"*
should not commit us to writing about a selloff.

One pick produces one article. The rail is handed a portfolio narrowed to that
single vector, which takes its reuse path — no re-run of t0 or synthesis, and
nothing else the router could promote. A pick is an instruction, not a hint to a
ranker.

### Composing a vector yourself

Synthesis decides which candidates belong together, and it is sometimes wrong — it
split a telescope's hardware failure from that same telescope's landmark observation
into two vectors, promoted one, and dropped the other.

`--compose` is the escape hatch: you pick raw **t0 pool** items and declare them one
story. That grouping is final and synthesis never sees it (so `--compose` skips the
synthesis cost entirely). It **reuses the latest pool** so menu numbers stay stable;
pass `--fresh` only when you intentionally want a new discovery run first.

```bash
python -m algent_backend.cli newsroom run --to menu --pool-menu
```

```bash
python -m algent_backend.cli newsroom run --compose 88+114 --angle "a dying telescope still doing landmark work"
```

With `--compose`, `--angle` becomes the vector's **thesis** — you are hand-assembling
the vector, so what you say the story is *is* the story. Without one, the item labels
are joined with an instruction to cover them as a single piece.

### Picking from the vector menu

`+` joins vectors into one article (`--pick 3+7,12` makes two articles, the first
from vectors 3 and 7 merged — questions, hits and sources unioned). `--angle "…"`
prepends an operator steer to the picked vector's thesis, for when the framing
you want is not the framing synthesis chose.

An out-of-range or non-numeric pick is a hard error. That is deliberate — a
silently dropped pick would produce a successful-looking run that wrote about
something nobody chose.

## Publishing

Publishing is **on by default**, because the live site is the review surface.
`--to editorial` stages without shipping. To pull something down after the fact,
use `site retract` rather than avoiding publication up front.

## Things that will bite you

**Do not hit GDELT before a discovery run.** The `beats` channel sweeps GDELT
DOC, which enforces a shared, stateful, escalating rate limit. Anything that
queries DOC unpaced beforehand — including a separate agent that does its own
searching — makes the sweep fail wholesale with `rate_limited` and zero hits. A
beat channel returning nothing is almost always this, and almost never the beats
being dead. If it happens, wait a few minutes and re-run; do not re-run the full
pipeline to fix a discovery problem.

**There is no "discovery agent" to launch first.** Discovery starts at `t0`
inside this command. The retired `general_discovery` agent used to look like the
entry point and was exactly the unpaced-DOC offender described above.

**`--dry-run` is free.** Use it whenever you are unsure what a flag combination
will do. Nothing else on the ladder is free past `t0`.

## Extending it

New downstream pipes (video, audio) are one entry appended to `STAGES` in
`backend/algent_backend/cli/newsroom/pipeline.py`. They inherit every `--from`
/`--to` combination automatically; no new flags and no new commands.
