"""Position ingesters for the always-on stream service: each module turns one outside source into reports on the boards
(``board.VesselBoard.report`` / ``sky.SkyBoard.ingest_*``). Sources are merged by identity (MMSI, ICAO address), freshest wins."""
