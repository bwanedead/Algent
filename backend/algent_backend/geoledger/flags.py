"""
Operator knobs of the geoledger (in-repo, not ``.env``).

``ENABLED``  the daily reads its sections into the ledger (one cheap model call per section). Off, the ledger still serves
             what it has, and ``newsroom geo extract`` still works by hand.
"""

ENABLED = True
