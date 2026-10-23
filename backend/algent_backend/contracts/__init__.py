"""
Versioned contracts between the server's published documents and the site's parsers (docs/architecture/foundation.md, "Contracts between server and site").

* the declarations: ``Product.contracts`` in the product registry (schema id, major version, path patterns, older majors the site still reads);
* ``shapes.SHAPES``: what the site reads of each schema, in the tiny language of ``spec.py``;
* ``examples.EXAMPLES``: one typed example document per schema, checked against the shapes in tests and run through the site's own TypeScript parsers;
* ``resolve``: path -> contract, and the stamp a document carries.

Rule: a breaking change (a field renamed, removed or retyped) bumps the MAJOR; an additive change does not. A document without a ``schema`` is a legacy v1.
"""

from __future__ import annotations

from .resolve import find, normal, parse_stamp, site_table, stamp_for, view_schema
from .spec import validate

__all__ = ["find", "normal", "parse_stamp", "site_table", "stamp_for", "validate", "view_schema"]
