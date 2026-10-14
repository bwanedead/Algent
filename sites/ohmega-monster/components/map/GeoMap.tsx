"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { eventLayers, liveFeatureId } from "@/components/live/eventLayers";
import { setMapUp, useScope } from "@/components/live/theaterLive";
import type { DailyDevelopment, TheaterMap } from "@/lib/daily";

import GeoMapStatic from "./GeoMapStatic";
import LiveMap, { type MapStatus } from "./LiveMap";
import { theaterLayers } from "./theaterLayers";

// THE map of the site: daily-report theaters and dossier maps both draw through this. It is the interactive map
// (MapLibre over OpenFreeMap tiles, see LiveMap.tsx) showing the backend's data: numbered marks that match the
// development list, disputed/occupied areas, chokepoint readings. While it loads a neutral skeleton holds the place (no static map to flash
// before the real one); the home-drawn SVG (GeoMapStatic) shows only without JS (<noscript>) or WebGL, and in full
// (with its own legend and credit) if the interactive map cannot start. The SVG also stays the source for social stills.
// The theater's live events (its "Live now" strip, see components/live/theaterLive.ts) are drawn on it the way /live draws them, and the
// strip's "Show me" makes this map fly to one and open its popup (LiveMap `reveal`); the events arrive with the page, so no extra fetch.
// Doctrine: docs/ethos/information-ergonomics-ethos.md. Spec: docs/architecture/intel-desk.md "Maps".

const BASEMAP_CREDIT = "Interactive basemap: OpenFreeMap, © OpenMapTiles, data © OpenStreetMap contributors.";

export default function GeoMap({ map, developments, label, initialK, liveScope }: { map: TheaterMap | null; developments: DailyDevelopment[]; label?: string; initialK?: number; liveScope?: string }) {
  const [status, setStatus] = useState<MapStatus>("loading");
  const spec = useMemo(() => (map ? theaterLayers(map, developments) : null), [map, developments]);
  const { events, request } = useScope(liveScope);
  const liveSpecs = useMemo(() => eventLayers(events), [events]);
  const layers = useMemo(() => (spec ? [...spec.layers, ...liveSpecs] : []), [spec, liveSpecs]);
  const items = useMemo(
    () => (spec ? [...spec.items, ...events.filter((e) => e.lat !== null && e.lon !== null).map((e) => ({ id: liveFeatureId(e.id), label: `Live: ${e.title}` }))] : []),
    [spec, events],
  );
  const fig = useRef<HTMLElement>(null);
  const seen = useRef(request?.nonce ?? 0); // a request filed before this map existed is not replayed
  const fresh = request && request.nonce > seen.current ? request : null;
  const ready = status === "ready";

  useEffect(() => {
    if (!liveScope || !ready) return;
    setMapUp(liveScope, true);
    return () => setMapUp(liveScope, false);
  }, [liveScope, ready]);

  // A "Show me" press: bring the map into view first (the strip sits above it); the map itself then flies to the event.
  useEffect(() => {
    if (!fresh) return;
    const calm = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    fig.current?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "nearest" });
  }, [fresh?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!map || !spec) return null;
  if (status === "failed") return <GeoMapStatic map={map} developments={developments} label={label} initialK={initialK} />;

  const name = label ?? `Map: ${map.points.length} marked place${map.points.length === 1 ? "" : "s"}, numbered as in the timeline.`;
  const hasAreas = map.disputed.length > 0;
  const aspect = Math.min(1.9, Math.max(1.1, map.width / map.height));
  return (
    <figure className="geo-map geo-map-int" ref={fig}>
      <LiveMap
        layers={layers}
        bounds={spec.bounds}
        label={name}
        aspect={aspect}
        tilt
        maxZoom={8}
        items={items}
        itemsLabel="Marked places"
        reveal={fresh ? { nonce: fresh.nonce, id: liveFeatureId(fresh.id) } : null}
        onStatus={setStatus}
        fallback={<GeoMapStatic map={map} developments={developments} label={name} initialK={initialK} bare />}
        credit={
          <>
            <span className="geo-micro">Numbers match the timeline. Solid mark: researched; hollow: reported.{hasAreas ? " Dashed purple areas: disputed or occupied territory; select one for its status and source." : ""}</span>
            {events.length > 0 && <span className="geo-micro"> Red, amber and purple dots: live events from the strip above (outages, earthquakes, fires, aircraft).</span>}
            <br />
            {map.credit} {BASEMAP_CREDIT}
          </>
        }
      />
    </figure>
  );
}
