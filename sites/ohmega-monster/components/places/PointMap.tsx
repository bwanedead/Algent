"use client";

import { useMemo } from "react";

import { assetLayer } from "@/components/map/assetLayers";
import { collection, pointFeature, type Bounds } from "@/components/map/geo";
import LiveMap from "@/components/map/LiveMap";
import type { LayerSpec } from "@/components/map/mapLayers";
import type { GeoAsset } from "@/lib/geoledger-shared";

// A small map of one thing: a place (drawn like the theater maps draw it: lettered, coloured by its latest status) or a
// plain dot for where a development happened. Same interactive map as everywhere else; the framed area is a few
// degrees around the point, wider when the position is only approximate.

const MARK = "#c2410c"; // the daily maps' vermilion
const BASEMAP_CREDIT = "Basemap: OpenFreeMap, © OpenMapTiles, data © OpenStreetMap contributors.";

type Props = { lat: number; lon: number; label: string; asset?: GeoAsset; spread?: number; note?: string };

export default function PointMap({ lat, lon, label, asset, spread = 0.6, note }: Props) {
  const layers = useMemo<LayerSpec[]>(() => {
    if (asset) {
      const l = assetLayer([asset], [], new Date(), false);
      return l ? [l] : [];
    }
    return [{ group: "point", kind: "dots", color: MARK, halo: true, data: collection([pointFeature([lon, lat], { id: "pt", r: 8, name: label })]) }];
  }, [asset, lat, lon, label]);
  const bounds: Bounds = [lon - spread * 1.6, lat - spread, lon + spread * 1.6, lat + spread];
  return (
    <figure className="geo-map geo-map-int">
      <LiveMap layers={layers} bounds={bounds} label={label} aspect={1.9} maxZoom={12} theaterStyle credit={<span className="geo-micro">{note ? `${note} ` : ""}{BASEMAP_CREDIT}</span>} />
    </figure>
  );
}
