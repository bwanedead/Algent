"""
Source fetchers. An observation source is ``fetch(indicators, today) -> {indicator id: [Observation] | error text}``
(one network failure inside a source is reported per indicator; a blocked source raises
``SourceUnavailable``). Wikidata is the odd one out: it yields leaders, not indicator observations.
"""

from . import bis, imf, owid, wikidata, wits, worldbank

#: key -> observation fetcher; the key is also ``Indicator.source``.
OBSERVATION_SOURCES = {"wb": worldbank.fetch, "owid": owid.fetch, "imf": imf.fetch, "bis": bis.fetch}
LEADER_SOURCE = "wikidata"
TRADE_SOURCE = "wits"      # ranked trade lines, not indicator observations: its own collector path

__all__ = ["LEADER_SOURCE", "OBSERVATION_SOURCES", "TRADE_SOURCE", "bis", "imf", "owid", "wikidata", "wits", "worldbank"]
