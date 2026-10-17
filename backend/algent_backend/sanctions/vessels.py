"""
Vessel designations -> the geoledger. A designated ship becomes (or joins) an asset of type ``vessel`` with a ``designated``
status event whose claimant is the list's publisher, so the place/asset views carry the sanction beside everything else
known about the ship. Delistings are not recorded there (the ledger has no "no longer designated" status).
"""

from __future__ import annotations

from algent_backend.geoledger import contracts as gc
from algent_backend.geoledger.ingest import add_event
from algent_backend.geoledger.store import Ledger

from .contracts import SanctionsEvent

CLAIMANT = {"ofac": "US Treasury OFAC", "uk": "UK FCDO / OFSI", "eu": "EU Council"}
SOURCE_LABEL = {"ofac": "OFAC SDN list", "uk": "UK Sanctions List", "eu": "EU consolidated sanctions list"}


def asset_key(imo: str, name: str, flag: str) -> str:
    """The ledger id of a ship: by IMO number when known (the same ship on three lists is one asset)."""
    return f"og-xx-vessel-imo{imo}" if imo else gc.new_asset_id(name, "vessel", flag)


def asset_id(e: SanctionsEvent) -> str:
    return asset_key(e.imo, e.name, e.flag)


def link(events: list[SanctionsEvent], ledger: Ledger | None = None) -> dict[str, int]:
    """Record each designated vessel as an asset + a ``designated`` event. Idempotent (ids are deterministic). Never raises."""
    ledger = ledger or Ledger()
    done = {"assets": 0, "events": 0, "skipped": 0}
    try:
        for e in events:
            if e.type != "vessel" or e.action != "designated":
                continue
            aid = asset_id(e)
            if aid not in ledger.assets:
                attrs: dict[str, str | float | int] = {"programme": ", ".join(e.programmes)[:80]}
                attrs.update({k: v for k, v in (("imo", e.imo), ("owner", e.owner)) if v})
                done["assets"] += ledger.add_assets([gc.Asset(
                    id=aid, name=e.name, type="vessel", country=e.flag, precision="unplaced", attrs=attrs,
                    source=f"{SOURCE_LABEL[e.source]} (sanctions feed)", licence="official public list", source_url=e.source_url,
                    provenance="aggregated")])
            try:
                add_event(ledger, aid, status="designated", claimant=CLAIMANT[e.source], occurred_on=e.date, sources=[e.source_url],
                          confidence="high", note=f"Listed under {', '.join(e.programmes) or 'a sanctions programme'}"[:gc.NOTE_CHARS],
                          via=f"sanctions:{e.source}")
                done["events"] += 1
            except ValueError:
                done["skipped"] += 1
    except Exception:  # noqa: BLE001 - the ledger link is an addition; the sanctions events are already stored
        done["skipped"] += 1
    return done
