# Topic freeze (dev hard-block)

**Purpose:** during 1-article-at-a-time polishing, stop one mega-beat (e.g. Iran/Hormuz)
from winning every rail. Lines below are frozen until **you delete them**.

This is separate from published-headline cooldown (agent-semantic). Freeze is
operator-controlled and hard: matching vectors cannot promote.

## How to edit
- One topic per line starting with `-` or `*`.
- Matching is **case-insensitive substring** against vector title + thesis + rationale.
- Blank lines and `#` comments are ignored.
- Remove a line to unfreeze that family.
- Optional: set `ALGENT_TOPIC_FREEZE=0` to ignore this file entirely.

## Frozen topics (edit freely)

### Iran conflict / US–Iran kinetic track
- iran strike
- strikes on iran
- us-iran
- u.s.-iran
- u.s. strikes on iran
- us strikes on iran
- iran war
- iran conflict
- war with iran
- against iran
- iranian targets
- night of strikes on iran

### Hormuz / energy-war shipping theater (same beat family for now)
- hormuz
- strait of hormuz
- tanker traffic
- bab al-mandeb
- houthi ultimatum
- israel-iran ceasefire
- israel x iran
- iran ceasefire

# Add more below as you freeze beats during dev:
# - ice detention
# - ice arrest
