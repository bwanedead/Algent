"""
Elections feed: opinion polls, poll averages and results for the elections that are about to happen or just did, read from Wikipedia's wikitext.

The electoral calendar (``lookahead``) says which elections are near; for each, ``collect`` fetches the election's own page and its "Opinion polling for
the ..." page (``action=raw``), ``polls`` / ``results`` pull the tables apart, and ``store`` appends one snapshot per election whenever its content changed.
Volunteer-compiled, so every figure is ``medium`` confidence and carries a CC BY-SA 4.0 attribution link; raw cells are kept where a row did not parse.
Nothing here is published to R2: the corpus adapter (``corpus/sources/elections.py``) is how the bots read it. See docs/architecture/elections.md.
"""
