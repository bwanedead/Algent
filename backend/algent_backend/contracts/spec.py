"""
A tiny shape language for published documents (stdlib only; docs/architecture/foundation.md, "Contracts between server and site").

A *spec* is plain data:

* a string names a type: ``str`` ``int`` ``num`` (int or float, never bool) ``bool`` ``obj`` ``list`` ``any`` ``date`` (``YYYY-MM-DD``); ``a|b`` is either,
  ``null`` allowed as a member (``str|null``); ``in:x,y`` is one of the listed strings;
* a dict is an object: each key must be present with a value matching its spec; a key ending ``?`` may be absent; keys the spec does not name are allowed
  (an *additive* change never fails a contract); the key ``"*"`` makes every value of a mapping match its spec;
* a one-element list ``[spec]`` is an array each of whose items (the first ``ITEMS_CHECKED``) matches the spec.

``validate(doc, spec)`` returns the list of problems (``$.rows[0].id: missing``), empty when the document fits. A spec lists what the site *reads*, so a rename
or a type change on either side shows up as a problem; fields the site ignores are left out on purpose.
"""

from __future__ import annotations

import re
from typing import Any

#: A long array is checked on its first items only (the writer builds every item the same way; the rest would only cost time).
ITEMS_CHECKED = 50
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "num"
    if isinstance(value, str):
        return "str"
    if isinstance(value, dict):
        return "obj"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def _atom(value: Any, name: str) -> bool:
    if name == "any":
        return True
    if name.startswith("in:"):
        return isinstance(value, str) and value in name[3:].split(",")
    if name == "num":
        return _kind(value) in ("int", "num")
    if name == "date":
        return isinstance(value, str) and bool(_DATE.match(value))
    return _kind(value) == name


def validate(doc: Any, spec: Any, path: str = "$") -> list[str]:
    """Problems of ``doc`` against ``spec`` (see the module doc); [] when it fits."""
    if isinstance(spec, str):
        names = spec.split("|") if not spec.startswith("in:") else [spec]
        return [] if any(_atom(doc, n) for n in names) else [f"{path}: expected {spec}, got {_kind(doc)}"]
    if isinstance(spec, list):
        if not isinstance(doc, list):
            return [f"{path}: expected a list, got {_kind(doc)}"]
        return [p for i, item in enumerate(doc[:ITEMS_CHECKED]) for p in validate(item, spec[0], f"{path}[{i}]")]
    if isinstance(spec, dict):
        if not isinstance(doc, dict):
            return [f"{path}: expected an object, got {_kind(doc)}"]
        out: list[str] = []
        if "*" in spec:
            for k, v in list(doc.items())[:ITEMS_CHECKED]:
                out += validate(v, spec["*"], f"{path}.{k}")
        for key, sub in spec.items():
            if key == "*":
                continue
            name, optional = (key[:-1], True) if key.endswith("?") else (key, False)
            if name not in doc:
                if not optional:
                    out.append(f"{path}.{name}: missing")
                continue
            out += validate(doc[name], sub, f"{path}.{name}")
        return out
    raise TypeError(f"bad spec at {path}: {spec!r}")
