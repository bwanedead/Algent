# Maritime behaviour (shadow-fleet watch)

Original intelligence from the AIS we already hear: which vessels went dark inside heard water, met another ship in open water, changed identity,
matched a sanctions designation, or loitered over sensitive infrastructure. Derived by Ohmega (provenance `ohmega_derived`, claimant "Ohmega analysis"),
forward-only, no model. Code: `backend/algent_backend/maritime/`; CLI: `newsroom maritime ...`; migration `013_maritime_events.sql`; site: `/live` "Shadow fleet"
layer (off by default), `/intel/maritime`, vessel place pages, `/api/v1/maritime`, MCP `get_maritime_behaviour`.

An event is **a pattern seen, never a finding of intent**. Every event carries a confidence (0..1), a one-sentence `rationale` with the numbers that fired it,
a plain `summary`, the `detail` numbers each detector used and its evidence points (`[unix seconds, lat, lon, knots, note]`). Every threshold is in
`maritime/flags.py` with its reason, so retuning after a few weeks of real traffic is one edit.

## Where it runs and what it keeps

The detectors run **inside the stream service** (`newsroom live ais`, unit `ohmega-ais`), because only it holds the live board and the receiver-coverage
grid. The vessel board tells the `Watch` every broadcast identity (static messages and names carried on position messages); once a cycle the watch folds the
board's rows into the **profile book** and, every `DETECT_SECONDS` (5 min), runs the detectors. The timer runner (`live/runner.py`) only publishes.

| Store (`ALGENT_MARITIME_STORE`, default `maritime_store/`) | What |
|---|---|
| `profiles.json.gz` | per MMSI: IMO, name, ship type, identity changes (name / IMO / type family), last position + speed + time, at most one position sample an hour (a ship that sits still keeps ONE sample), capped at 96. Expires 4 days after last heard; at most 50 000 profiles (freshest kept); written every 15 min atomically. Place activity (underway samples per 1-degree cell per hour) is rebuilt from the samples on load |
| `state.json` | open work between passes: slow encounters, dwell trackers, `last_cycle`, `blind_until` |
| `events.json` | the CURRENT picture: events of the last 30 days, at most 3 000, by id |
| `log.jsonl` | append-only: a line when an event is first seen or changes state |
| `published.json` | watermark (newest `updated_at` sent to the site database) |

## Detectors

| Kind | Fires when | Screened out (coverage honesty) |
|---|---|---|
| `ais_gap` | underway (>= 2 kn) at its last report, silent >= 6 h, in a 3 x 3 degree block that held >= 2 underway samples an hour from OTHER vessels before and kept >= half that rate during the silence, and the block was heard within the last hour. Closed when heard again, with how far it reappeared (>= 30 km = moved while dark) | left receiver coverage / the place went quiet as a whole (activity fell), thin water, a ship that stopped, port and coast areas, silences that began before the stream's own downtime (`blind_until`) |
| `sts` | tanker + tanker / cargo / unknown-type, both <= 1.5 kn, <= 500 m apart, for >= 2 h, outside port areas | ports and harbour approaches, crowds (>= 6 other slow ships within 5 km: an anchorage), tugs / pilots / fishing / passenger partners, a convoy underway; pairs together > 36 h are halved (lay-up) |
| `identity` | rename (name differs beyond truncation / a typo), a name that returns to an earlier one (alternating), an IMO that changed on one MMSI, an invalid IMO check digit, one IMO under MMSIs of different flag states | names under 4 characters, prefixes (AIS truncation), 75% character similarity |
| `sanctioned` | the profile's IMO is a designated vessel's IMO (confidence .95), or exact name (including former names) AND flag state (MID) match (.55). One event per vessel, listing and UTC day | a name alone is never reported |
| `loiter` | <= 3 kn for >= 4 h inside a chokepoint box (`live/regions.py` gates) or a cable / pipeline corridor proxy (`sites.ZONES`), outside port areas | crowds (anchorage), fishing / towing / dredging / diving / special craft |

The cable boxes are **approximate corridors, not surveyed routes** (marked "proxy"): replace them with a cable-route dataset when one exists. Port exclusion
uses the geoledger's `port` assets (10 km) and a land probe against the Natural Earth basemap (6 km); with neither, nothing is excluded, so seed OSM ports
(`newsroom geo seed --source osm`) on the server. A vessel with more than one kind of flag is raised (`detail.related`; a sanctions match +0.2, others +0.1), computed
afresh each pass from `detail.base_conf` so it never ratchets.

## Publish and the brain

* `maritime_events` (migration 013, anon select only): upserted by the timer runner when the events file changed; ended events pruned after 30 days.
* Geoledger: an event on a vessel the ledger already knows (a sanctioned vessel, or any whose IMO has an asset) is added as a `behaviour_flagged` status event
  (claimant "Ohmega analysis", `ohmega_derived`). It never creates an asset and never becomes an asset's current status (`geoledger.contracts.latest`).
* Daily: `OHMEGA MARITIME` evidence block (`maritime/desk.py`, wired in `agent_system/agents/intel/sensing.py`) for theaters whose countries the events' area touches,
  and the strongest events anywhere for the world sweep. The doctrine bullet in `daily.py` says to cite it as "Ohmega analysis" and not to read intent into it.

## Known limits

AIS is what volunteer and coastal receivers hear: open ocean is mostly unseen, which is exactly why a gap is judged against neighbours still being heard. Spoofed
positions are not detected. Class B ships send their name and type in separate parts; truncated names are treated as the same ship. Flag state is the MMSI's
radio identity (flags of convenience show as such). A first-run store has no history: gaps need hours of activity to judge, so the first days under-report.
