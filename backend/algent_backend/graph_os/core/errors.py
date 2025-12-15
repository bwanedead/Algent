"""
GraphOS specific exception hierarchy.
"""


class GraphOSError(Exception):
    """Base error for the graph substrate."""


class GraphInvariantError(GraphOSError):
    """Raised when invariants are violated."""


class VocabularyError(GraphOSError):
    """Raised when vocabulary constraints fail."""
