"""
GNSS interference (GPS jamming and spoofing) — read from the navigation integrity that aircraft broadcast.

An aircraft's ADS-B position message carries NACp/NIC: how well it trusts its own position. Under jamming the receiver on board degrades, so the
share of aircraft in a place reporting poor accuracy rises. ``collect`` samples ADS-B (adsb.lol) around known trouble spots and control areas each
hour, ``zones`` turns a day's samples into cells with a severity and a flag against that cell's own learned normal, and ``gpsjam`` reads GPSJam.org's
daily file as an independent cross-check. The ADS-B derivation is Ohmega's own (basis ``our_estimate``); coverage is partial by construction
(volunteer receivers, our sample points), so zones are a minimum. See ``docs/architecture/conflict-events-gnss.md``.
"""
