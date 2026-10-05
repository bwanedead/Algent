"""
Source fetchers. An observation source is ``fetch(indicators, today) -> {indicator id: [Observation] | error text}``
(one network failure inside a source is reported per indicator; a blocked source raises
``SourceUnavailable``). Wikidata is the odd one out: it yields leaders, not indicator observations.
"""

from . import imf, owid, wikidata, worldbank

#: key -> observation fetcher; the key is also ``Indicator.source``.
OBSERVATION_SOURCES = {"wb": worldbank.fetch, "owid": owid.fetch, "imf": imf.fetch}
LEADER_SOURCE = "wikidata"

__all__ = ["LEADER_SOURCE", "OBSERVATION_SOURCES", "imf", "owid", "wikidata", "worldbank"]
