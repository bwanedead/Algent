"""
Search channel policy — hard per-agent permission gates on the web_search facade.

The facade hides several API surfaces (Tavily, Exa, Firecrawl, X). Different
agents should be trusted with different ones — a cheap scout might get only free
keyword search + free reads, while a high-value researcher gets semantic, rich
(Firecrawl), and X. This module is the gate: a per-execution allow-set the facade
checks before touching any channel.

Two deliberate defaults, both safety rails:
- **Paid channels are off by default.** ``rich`` (Firecrawl) and ``x`` must be
  *explicitly granted* to an agent — so no agent can drain credits unless someone
  decided it should. This is the paid-api-sparingly ethos enforced in code.
- A disallowed channel is a **hard refusal**, not a silent downgrade — the agent
  gets a clear "not permitted" result it can reason about.

The allow-set is held in a ``ContextVar`` so the runtime can scope it to the agent
it is about to run; tests set it directly.
"""

from __future__ import annotations

import contextvars

# The gateable channels (intent names; provider in parentheses).
KEYWORD = "keyword"  # Tavily
SEMANTIC = "semantic"  # Exa
READ = "read"  # trafilatura — free
RICH = "rich"  # Firecrawl — paid
X = "x"  # native X — paid

ALL_CHANNELS = frozenset({KEYWORD, SEMANTIC, READ, RICH, X})
# Free + cheap only. Paid (RICH, X) is opt-in per agent.
DEFAULT_CHANNELS = frozenset({KEYWORD, SEMANTIC, READ})

_allowed: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar(
    "search_allowed_channels", default=DEFAULT_CHANNELS
)


def normalize(channels: object) -> frozenset[str]:
    """Coerce a channel spec to a valid allow-set (None -> default)."""
    if channels is None:
        return DEFAULT_CHANNELS
    return frozenset(channels) & ALL_CHANNELS


def set_allowed(channels: object) -> contextvars.Token:
    """Scope the allow-set for the current execution; returns a reset token."""
    return _allowed.set(normalize(channels))


def reset_allowed(token: contextvars.Token) -> None:
    _allowed.reset(token)


def allowed() -> frozenset[str]:
    return _allowed.get()


def is_allowed(channel: str) -> bool:
    return channel in _allowed.get()
