"""
GraphOS specific exception hierarchy.
"""


class GraphOSError(Exception):
    """Base error for the graph substrate."""


class GraphInvariantError(GraphOSError):
    """Raised when invariants are violated."""


class VocabularyError(GraphOSError):
    """Raised when vocabulary constraints fail."""


class VersionMismatchError(GraphOSError):
    """Raised when optimistic concurrency expectations fail."""

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"expected graph version {expected}, found {actual}")
        self.expected = expected
        self.actual = actual
