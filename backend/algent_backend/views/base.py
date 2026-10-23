"""
What a view is: a key, a family and a JSON body that opens with the same envelope.

    {"schema": "ohmega.view.<family>/1", "built_at": ..., "as_of": ..., "provenance": {...}, ...the view's own fields...}

``as_of`` is the date of the newest input (a view built from the same record is the same document). ``built_at`` is when this *content* was first built:
the publisher keeps the previous one while the content is unchanged (``publish.stamp``), so an unchanged view hashes the same and costs no upload.
``provenance`` names the products and documents the view was derived from; the records inside carry their own source URLs and ``basis`` fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from algent_backend.contracts import view_schema

from . import flags


@dataclass
class View:
    key: str                              # the path under the views prefix, without the extension: "country/FR"
    family: str                           # a key of flags.BUDGET_BYTES
    body: dict[str, Any]
    notes: list[str] = field(default_factory=list)

    @property
    def path(self) -> str:
        """The document path ``object_docs.publish`` stores (``views/country/FR.json`` -> ``docs/views/country/FR.json.gz``)."""
        return f"{flags.PREFIX}/{self.key}.json"

    def size(self) -> int:
        return len(json.dumps(self.body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))

    def over_budget(self) -> str:
        n, cap = self.size(), flags.BUDGET_BYTES[self.family]
        return f"{self.path}: {n:,} bytes is over the {cap:,} byte budget of the {self.family} family" if n > cap else ""


def make(family: str, key: str, body: dict[str, Any], *, as_of: str, sources: list[tuple[str, str]]) -> View:
    """A view with its envelope. ``sources`` is ``[(registry product id, document path or store)]``."""
    env = {"schema": view_schema(family), "built_at": "", "as_of": as_of or "",
           "provenance": {"builder": "algent_backend.views", "sources": [{"product": p, "from": f} for p, f in sources]}}
    return View(key=key, family=family, body={**env, **body})
