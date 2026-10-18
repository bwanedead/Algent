# Flows — the world's circulation

> Code: `backend/algent_backend/flows/` (tracker, network, rates, document, trade), the hook in `live/stream.py`,
> `cli/newsroom/flows.py`, `infra/server/install_schedules.sh` (`ohmega-flows`). Site: `sites/ohmega-monster/components/flows/`
> (canvas layer, legend), the globe's **Flows** button (`components/globe/GlobeViewer.tsx`) and the HUD panel
> `components/hud/panels/FlowsPanel.tsx`. Tests: `backend/tests/test_flows.py`.

Two kinds of flow, kept apart in the data, in the document and on the screen:

| | Ships | Grain and money |
|---|---|---|
| Source | **our own observed AIS** (the `ohmega-ais` stream service) | UN Comtrade public preview API, keyless |
| Nature | live-ish: dots moving along lanes, counted per day | annual values the exporting country reported |
| Drawn as | thin breathing lanes + moving dots, one hue per ship class | wide, slow, translucent arcs with an arrowhead, labelled with value and year |
| Refresh | the tracker runs every 5 min; the document is rebuilt every 15 min | weekly (`TRADE_REFRESH_DAYS`) |

## Ships: from positions to lanes

1. **Places** (`flows/network.py`). 51 boxes the ships are watched in: the six live gates (Hormuz, Bab el-Mandeb, Suez, Bosporus, Malacca,
   Taiwan Strait), eight more chokepoints (Panama, Gibraltar, Dover, the Danish straits, Dardanelles, Singapore, Sunda, Lombok) and 37 port
   regions (Persian Gulf, US Gulf, Rotterdam's North Sea, East China...). A chokepoint wins over the region around it.
   Boxes are generous because terrestrial AIS is heard only near volunteer stations; open ocean is not listened to.
2. **Lanes.** 71 hand-set sea lanes join neighbouring places, each with waypoints that keep its drawn path on the water (around
   capes, through straits). They are approximate (about 100 km). `network.route(a, b)` is the shortest sea path between any two places.
3. **Hops** (`flows/tracker.py`). Every 5 minutes the tracker looks at each trade carrier on the vessel board. A ship inside a place that
   is not the place it was last in has made a hop; each lane on `route(last, now)` gets one count for that day and ship class
   (*observed* when the two places are neighbours, *inferred* when the hop spans several lanes: the ship was lost over open water).
   The place entered gets a *visit*. A hop is dropped when it took longer than 21 days or needs more than 27 knots (a spoofed or re-used
   identity), and leaving a place and coming straight back inside 6 hours is one visit, not two hops.
4. **What is kept** (small; the server has 4 GB and Supabase is shared). Per vessel: the place it was last in and when (gzip JSON, bounded:
   14 days, 200 000 ships). Per day: lane counts by class, visit counts by place and class, the seconds the tracker was watching, and the
   last 8 durations of observed hops per lane. **No tracks.** Files: `live_store/flows/{tracker.json.gz, days.json}`.
5. **Rates** (`flows/rates.py`). Count divided by the time actually watched, per 24 h, over 7 and 30 days (a day the service was down is
   neither a halving nor a collapse). **Anomaly:** a place's latest complete watched day against the median and spread of its earlier
   watched days (up to 30) with live memory's own robust modified z (`live/memory/robust.py`) and the same cut (`Z_ENTER` 3.5). A place with
   fewer than 7 earlier watched days is not scored yet; the document says `learning`.

**Ship classes** (`flows/classes.py`): AIS type 80-89 is a tanker (a gas hint in the name makes it a gas carrier: `LNG`, `LPG`...), 70-79 is
cargo, and the broadcast name moves it to container (`MAERSK`, `MSC`, `COSCO`...) or bulk (`BULK`, `ORE`, `GRAIN`...). AIS never says "bulk"
or "container", so `bulk`, `container` and `lng` are floors and `cargo` is "cargo ship, kind not told". Passenger, fishing, military and
untyped vessels are not trade flows and are not counted.

**Coverage is patchy and the document says so** (`ais.note`). A ship dark across an ocean still counts on every lane between the two places
it was heard in, but a ship that never reappears is never counted. Read a lane against itself over time, never against the world's trade.

### Starting with history: `newsroom flows backfill`

The maritime profile book (`maritime_store/profiles.json.gz`) already holds an hourly position sample per moving ship for 4 days. The command
replays them through an **empty** tracker so the lane picture starts with days, not minutes (it refuses to run over existing counts: the same
crossings would count twice). Run it once on the server after the first deploy.

## Grain and money: UN Comtrade

`flows/trade/` asks `https://comtradeapi.un.org/public/v1/preview/C/A/HS` (no key, 500 rows a call, rate limited: 1.5 s between calls) for each
exporter's partner flows in its newest reported year (tries the last 3 years).

- **Grain** (HS 1001 wheat, 1005 maize, 1201 soybeans): 12 / 8 / 7 large exporters that file with Comtrade, the 5 strongest partners each,
  with tonnes (`netWgt`) and US dollars.
- **Money**: total goods exports (`TOTAL`) of the 20 largest exporters, their 4 strongest partners each, US dollars.
- An exporter that files nothing (Russia since 2022) is listed in `missing` and never estimated; an exporter that fails keeps its previous flows.
- 47 exporters, one to three calls each (a few minutes), weekly. Countries are placed at one hand-set point each (`trade/countries.py`; Comtrade's own codes such as
  France 251, India 699, "Other Asia, nes" 490 = Taiwan are mapped).
- Values are a **year of trade** as the reporter filed it, not a shipment; each exporter may be at a different year (the arcs say which).

Keyed or non-API sources that were considered and not used: USDA FAS Export Sales and GATS (weekly shipments by destination; needs an
api.data.gov key, which this repo does not hold: no key name in `docs/credentials.md`), USDA PSD bulk download (production and
total exports by country, no bilateral detail), AMIS Market Monitor (PDF), Ukraine's ministry export tallies (no stable machine feed). If an
FAS key is ever registered, weekly export sales would be a natural second grain source beside Comtrade's annual one.

## The document and its publish

`flows/document.py` builds one small JSON object (about 70 KB with a full trade picture): `ais` (places with visit rates and anomaly,
lanes with drawn path, 7/30-day rates by class, share inferred, median hours of observed hops, days watched, the coverage note), `grain`,
`money`, and `places` (the countries any arc mentions, with their points). `flows/publish.py` uploads it as `live/flows.json` to the public
`published-assets` bucket the way every live product goes (`live/snapshots.publish`; no migration, no table). The `ohmega-flows` timer
(every 15 min, free, outside the job lock) runs `newsroom flows publish`: refresh trade when due, build, upload. **A machine without lane
aggregates (a laptop) does not publish** unless `--allow-empty`, so it cannot replace the server's document with an empty one.

`newsroom flows status | lanes | trade [--force] | backfill | publish [--no-publish]`.

## The site

`/globe` gets a **Flows** button in its controls. It fetches `live/flows.json` (refreshing every 5 min while visible) and lays a transparent
canvas over the globe that reads the globe's own camera each frame, so it follows drag, zoom and the cycling views.

- **One hue per class, the same everywhere** (legend, canvas, HUD panel; `components/flows/style.ts`): tankers coral, gas carriers cyan,
  bulk carriers violet, container ships lime, other cargo slate; wheat gold, corn orange, soy green, money white. The site's coast amber and
  the anomaly rose and blue are not used for any class. Each class also keeps its own **strand** across a lane (and ships keep to the
  right of their direction), so a class is found by position as well as hue.
- **Density and rhythm are the observed rate.** A lane carrying `rate` ships a day over `km` at the class's typical speed has
  `rate x km / speed` ships on it at once; that is how many dots it gets, thinned by one global factor so the screen holds at most ~1 400
  (the legend says "1 dot is about N ships"). Busier lanes' lines also breathe faster (`0.12 + 1.2 x rate / busiest` cycles a second).
- **Anomalies glow.** A place whose latest day is outside its own normal gets a pulsing ring (rose above, blue below, the pair `/live` uses) and
  a plain label ("Strait of Hormuz: 17 ships on 17 Oct, usually 78"). Chokepoints are always labelled with their rate.
- **Grain and money** are off until switched on, drawn lifted off the globe with slow dashes and an arrowhead, width and strength by value,
  only each layer's largest flows (a reader budget), the largest few labelled with value and year.
- **Honesty line** in the legend: "as of", days watched, coverage patchy, "a year of trade, not live shipments".
- **Performance**: canvas 2D, `requestAnimationFrame`, no allocation per dot, paused when the tab is hidden or the globe is off screen,
  `prefers-reduced-motion` draws one static frame (redrawn only when the view, size, layers or data change). A frame costs ~2-6 ms in a
  Node harness with a stubbed context. No new npm dependencies.
- **HUD panel** "Ships, grain and money" (`FlowsPanel`): chokepoint rates with above/below flags, the busiest lanes, the largest grain
  and money flows. Off the default board; add it from the Panels menu.

`components/live`, `components/map` and the /live page are untouched, and so is the server's live density and points output.

## Left

- Real tracks per lane (the lane geometry is hand-set waypoints, not observed paths).
- Cargo from destination strings (`ShipStaticData.Destination` is in the static memory; it could tell a grain port from a refinery).
- Ship size (deadweight) would weight a lane by tonnage rather than hull count; AIS dimensions are not in the static memory yet.
- A second, weekly grain source (USDA FAS export sales) if a key is registered.
