"""
ResolvedModel — the output of resolution.

Wraps the concrete model object (``client``) alongside metadata about what was
built. We avoid returning a raw provider object directly: different targets
legitimately return different kinds of objects (a LangChain runnable now; a
direct SDK client later), and ``ResolvedModel`` keeps Algent honest about that
without forcing a premature universal interface.

Fields are kept minimal on purpose. Plausible future fields (capabilities,
warnings, construction metadata) are added only when a consumer actually reads
them — unused fields are speculative weight.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResolvedModel:
    """A resolved, ready-to-use model plus the metadata describing it."""

    provider: str
    target: str
    model: str
    client: Any
