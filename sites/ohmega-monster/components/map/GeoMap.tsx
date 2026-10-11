"use client";

import { useMemo, useState } from "react";

import type { DailyDevelopment, TheaterMap } from "@/lib/daily";

import GeoMapStatic from "./GeoMapStatic";
import LiveMap, { type MapStatus } from "./LiveMap";
import { theaterLayers } from "./theaterLayers";

// THE map of the site: daily-report theaters and dossier maps both draw through this. It is the interactive map
// (MapLibre over OpenFreeMap tiles, see LiveMap.tsx) showing the backend's data: numbered marks that match the
// development list, disputed/occupied areas, chokepoint readings. The home-drawn SVG (GeoMapStatic) is what you see while
// it loads, without JS or WebGL, and in full (with its own legend and credit) if the interactive map cannot start.
// Doctrine: docs/ethos/information-ergonomics-ethos.md. Spec: docs/architecture/intel-desk.md "Maps".

const BASEMAP_CREDIT = "Interactive basemap: OpenFreeMap, © OpenMapTiles, data © OpenStreetMap contributors.";

export default function GeoMap({ map, developments, label, initialK }: { map: TheaterMap | null; developments: DailyDevelopment[]; label?: string; initialK?: number }) {
  const [status, setStatus] = useState<MapStatus>("loading");
  const spec = useMemo(() => (map ? theaterLayers(map, developments) : null), [map, developments]);
  if (!map || !spec) return null;
  if (status === "failed") return <GeoMapStatic map={map} developments={developments} label={label} initialK={initialK} />;

  const name = label ?? `Map: ${map.points.length} marked place${map.points.length === 1 ? "" : "s"}, numbered as in the timeline.`;
  const hasAreas = map.disputed.length > 0;
  const aspect = Math.min(1.9, Math.max(1.1, map.width / map.height));
  return (
    <figure className="geo-map geo-map-int">
      <LiveMap
        layers={spec.layers}
        bounds={spec.bounds}
        label={name}
        aspect={aspect}
        tilt
        maxZoom={8}
        items={spec.items}
        itemsLabel="Marked places"
        onStatus={setStatus}
        fallback={<GeoMapStatic map={map} developments={developments} label={name} initialK={initialK} bare />}
        credit={
          <>
            <span className="geo-micro">Numbers match the timeline. Solid mark: researched; hollow: reported.{hasAreas ? " Dashed purple areas: disputed or occupied territory; select one for its status and source." : ""}</span>
            <br />
            {map.credit} {BASEMAP_CREDIT}
          </>
        }
      />
    </figure>
  );
}
