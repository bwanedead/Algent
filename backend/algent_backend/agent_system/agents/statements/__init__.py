"""
The statements ledger — who said what, collected from primary transcripts independent of which
theaters are hot. Rhetoric is a leading indicator; this is its record.

``collect`` gathers transcripts (free), ``extract`` turns each into statements (one model call),
``store`` keeps them append-only, ``recall`` serves writers an evidence block. Design:
docs/architecture/statements.md. Vision: docs/vision/ohmega-intelligence-engine.md ("Sensing").
"""

from .contracts import Statement, Transcript
from .recall import recall, speaker_history

__all__ = ["Statement", "Transcript", "recall", "speaker_history"]
