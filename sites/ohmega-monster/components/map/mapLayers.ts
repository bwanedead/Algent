// Declarative data layers for the shared interactive map (LiveMap.tsx): a LayerSpec is "this GeoJSON, drawn this way",
// and installLayer turns it into MapLibre sources/layers. Every feature that should be selectable carries an `id`
// property. Colours are passed in by the caller (map data colours are map-local, not theme tokens, like the SVG maps).
// Client-safe: no server imports.

/* eslint-disable @typescript-eslint/no-explicit-any -- MapLibre is loaded at runtime and untyped here */

import type { FeatureCollection, Props } from "./geo";

/** What a popup shows: the same plain detail the lists and cards show. `url` is opened only when http(s). */
export type PopupInfo = { kind?: string; title: string; when?: string; text?: string; lines?: string[]; url?: string; source?: string };

export type LayerKind =
  | "area" // polygons: translucent fill + outline (countries in an outage, disputed territory)
  | "line" // lines (+ an optional text label on point features of the same data)
  | "dots" // sized circles; `cluster` merges dense points into counted bubbles
  | "heat" // a heat surface that resolves into dots when zoomed in
  | "numbered"; // circles carrying a number, solid when researched and hollow when reported (the daily's marks)

export type LayerSpec = {
  /** Toggle unit: a group's map layers are shown or hidden together. */
  group: string;
  kind: LayerKind;
  data: FeatureCollection;
  color: string;
  dashed?: boolean;
  cluster?: boolean;
  /** Feature property whose text is drawn on a mark (`numbered`: the number) or beside a point (`line`). */
  labelProp?: string;
  /** Feature properties read by kind: `r` = circle radius in px (`dots`, default 6); `w` = weight (`heat`). */
  popup?: (p: Props) => PopupInfo | null;
};

export const FONT = ["Noto Sans Bold"]; // served by the OpenFreeMap glyph server for both styles
const ORDER: Record<LayerKind, number> = { area: 0, heat: 1, line: 2, dots: 3, numbered: 4 };
export const inDrawOrder = (specs: LayerSpec[]) => [...specs].sort((a, b) => ORDER[a.kind] - ORDER[b.kind]);

const sourceId = (g: string) => `lm-${g}`;
const geom = (t: string) => ["==", ["geometry-type"], t];

/** Add the spec's source and layers; returns the ids of the layers that accept clicks (and every layer id, for toggling). */
export function installLayer(map: any, spec: LayerSpec): { all: string[]; click: string[] } {
  const src = sourceId(spec.group);
  const id = (s: string) => `${src}-${s}`;
  const all: string[] = [];
  const click: string[] = [];
  const add = (layer: Record<string, unknown>, clickable = false) => {
    map.addLayer({ source: src, ...layer });
    all.push(layer.id as string);
    if (clickable) click.push(layer.id as string);
  };
  const clustered = spec.kind === "dots" && spec.cluster === true;
  map.addSource(src, { type: "geojson", data: spec.data, ...(clustered ? { cluster: true, clusterRadius: 44, clusterMaxZoom: 7 } : {}) });
  const label = spec.labelProp ? ["to-string", ["coalesce", ["get", spec.labelProp], ""]] : null;
  const halo = { "text-halo-color": "#ffffff", "text-halo-width": 1.6 };

  switch (spec.kind) {
    case "area":
      add({ id: id("fill"), type: "fill", filter: geom("Polygon"), paint: { "fill-color": spec.color, "fill-opacity": 0.3 } }, true);
      add({ id: id("edge"), type: "line", filter: geom("Polygon"), paint: { "line-color": spec.color, "line-width": 1.6, ...(spec.dashed ? { "line-dasharray": [3, 2] } : {}) } });
      break;
    case "line":
      add({ id: id("line"), type: "line", filter: geom("LineString"), layout: { "line-cap": "round" }, paint: { "line-color": spec.color, "line-width": ["interpolate", ["linear"], ["zoom"], 2, 3, 8, 5] } }, true);
      add({ id: id("pt"), type: "circle", filter: geom("Point"), paint: { "circle-radius": 7, "circle-color": spec.color, "circle-stroke-color": "#fff", "circle-stroke-width": 2 } }, true);
      if (label) add({ id: id("label"), type: "symbol", filter: geom("Point"), layout: { "text-field": label, "text-font": FONT, "text-size": 12, "text-offset": [0, 1.3], "text-anchor": "top", "text-optional": true }, paint: { "text-color": "#14282b", ...halo } });
      break;
    case "heat":
      add({ id: id("heat"), type: "heatmap", maxzoom: 9, paint: {
        "heatmap-weight": ["interpolate", ["linear"], ["coalesce", ["get", "w"], 1], 1, 0.35, 8, 1],
        "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 1, 8, 6, 22, 9, 34],
        "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 1, 0.9, 9, 2],
        "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(224,86,27,0)", 0.25, "rgba(255,196,80,0.55)", 0.6, "rgba(240,120,30,0.8)", 1, spec.color],
        "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 6, 0.9, 9, 0] } });
      add({ id: id("dots"), type: "circle", minzoom: 6, paint: { "circle-radius": 5, "circle-color": spec.color, "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 } }, true);
      break;
    case "dots":
      if (clustered) {
        add({ id: id("cluster"), type: "circle", filter: ["has", "point_count"], paint: { "circle-color": spec.color, "circle-opacity": 0.85, "circle-stroke-color": "#fff", "circle-stroke-width": 2, "circle-radius": ["step", ["get", "point_count"], 14, 10, 18, 40, 24] } }, true);
        add({ id: id("count"), type: "symbol", filter: ["has", "point_count"], layout: { "text-field": ["get", "point_count_abbreviated"], "text-font": FONT, "text-size": 12, "text-allow-overlap": true }, paint: { "text-color": "#ffffff" } });
      }
      add({ id: id("dots"), type: "circle", ...(clustered ? { filter: ["!", ["has", "point_count"]] } : {}), paint: { "circle-radius": ["coalesce", ["get", "r"], 6], "circle-color": spec.color, "circle-opacity": 0.9, "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 } }, true);
      break;
    case "numbered":
      add({ id: id("mark"), type: "circle", paint: {
        "circle-radius": 11, "circle-stroke-width": 2.5, "circle-stroke-color": spec.color,
        "circle-color": ["case", ["==", ["get", "verification"], "researched"], spec.color, "#ffffff"] } }, true);
      if (label) add({ id: id("num"), type: "symbol", layout: { "text-field": label, "text-font": FONT, "text-size": 12, "text-allow-overlap": true, "text-ignore-placement": true }, paint: {
        "text-color": ["case", ["==", ["get", "verification"], "researched"], "#ffffff", spec.color] } });
      break;
  }
  return { all, click };
}

export function removeLayer(map: any, spec: LayerSpec, ids: string[]) {
  for (const l of ids) if (map.getLayer(l)) map.removeLayer(l);
  const src = sourceId(spec.group);
  if (map.getSource(src)) map.removeSource(src);
}

export const SELECTED_SOURCE = "lm-selected";
export function installSelected(map: any) {
  map.addSource(SELECTED_SOURCE, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({ id: `${SELECTED_SOURCE}-ring`, source: SELECTED_SOURCE, type: "circle", paint: { "circle-radius": 17, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#111111", "circle-stroke-width": 3 } });
}

/** A popup's content as DOM nodes (text only: nothing from the data is ever parsed as HTML). */
export function popupNode(info: PopupInfo): HTMLElement {
  const root = document.createElement("div");
  root.className = "lm-pop";
  const el = (tag: string, cls: string, text: string) => {
    const n = document.createElement(tag);
    n.className = cls;
    n.textContent = text;
    root.appendChild(n);
    return n;
  };
  if (info.kind) el("p", "lm-pop-kind", info.kind);
  el("h3", "lm-pop-title", info.title);
  if (info.when) el("p", "lm-pop-when", info.when);
  if (info.text) el("p", "lm-pop-text", info.text);
  for (const line of info.lines ?? []) el("p", "lm-pop-line", line);
  if (info.url && /^https?:\/\//.test(info.url)) {
    const p = document.createElement("p");
    p.className = "lm-pop-src";
    const a = document.createElement("a");
    a.href = info.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = `${info.source || "Source"} ↗`;
    p.append("Source: ", a);
    root.appendChild(p);
  } else if (info.source) el("p", "lm-pop-src", `Source: ${info.source}`);
  return root;
}
