// Declarative data layers for the shared interactive map (LiveMap.tsx): a LayerSpec is "this GeoJSON, drawn this way",
// and installLayer turns it into MapLibre sources/layers. Every feature that should be selectable carries an `id`
// property. Colours are passed in by the caller (map data colours are map-local, not theme tokens, like the SVG maps).
// Client-safe: no server imports.

/* eslint-disable @typescript-eslint/no-explicit-any -- MapLibre is loaded at runtime and untyped here */

import type { FeatureCollection, Props } from "./geo";

/** What a popup shows: the same plain detail the lists and cards show. `url` is opened only when http(s). */
export type PopupInfo = { kind?: string; title: string; when?: string; text?: string; lines?: string[]; url?: string; source?: string; /** A page on this site about the thing (shown as a "More" link). */ href?: string };

export type LayerKind =
  | "area" // polygons: translucent fill + outline (countries in an outage, disputed territory)
  | "line" // lines (+ an optional text label on point features of the same data)
  | "dots" // sized circles; `cluster` merges dense points into counted bubbles
  | "heat" // a heat surface that resolves into dots when zoomed in
  | "icons" // heading-rotated icon images (ships, aircraft: the same arrows /live draws); `cluster` merges dense ones into counted bubbles
  | "numbered" // circles carrying a number, solid when researched and hollow when reported (the daily's marks)
  | "assets"; // infrastructure: a small disc per place coloured by `col`, faded by `op`, with its type's letter `g`

export type LayerSpec = {
  /** Toggle unit: a group's map layers are shown or hidden together. */
  group: string;
  kind: LayerKind;
  data: FeatureCollection;
  color: string;
  dashed?: boolean;
  /** `area`: a soft fill (low opacity, hairline edge) for context such as outages, not a hard shape. */
  soft?: boolean;
  /** `dots`: a faint wide halo under each dot (the dot itself stays small and crisp). */
  halo?: boolean;
  cluster?: boolean;
  /** `icons`: a muted, small drawing (small arrows/dots, low-contrast small clusters) for background context such as a theater's traffic. */
  subtle?: boolean;
  /** `icons`: registers the images the features' `ic` property names on the map (idempotent; called on every style load). The features
   *  carry `ic` (image name), `h` (heading in degrees, negative = unknown: drawn as a plain dot in `col`) and `col`. */
  images?: (map: any) => void;
  /** Feature property whose text is drawn on a mark (`numbered`: the number) or beside a point (`line`). */
  labelProp?: string;
  /** Feature properties read by kind: `r` = circle radius in px (`dots`, default 6; `assets`); `w` = weight (`heat`); `assets` also
   *  reads `col` (colour), `op` (opacity 0..1), `g` (the letter) and `ev` (events on record: places with one keep their letter at every zoom). */
  popup?: (p: Props) => PopupInfo | null;
};

export const FONT = ["Noto Sans Bold"]; // served by the OpenFreeMap glyph server for both styles
const ORDER: Record<LayerKind, number> = { area: 0, heat: 1, line: 2, dots: 3, assets: 3.2, icons: 3.5, numbered: 4 };
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
  const clustered = (spec.kind === "dots" || spec.kind === "icons") && spec.cluster === true;
  map.addSource(src, { type: "geojson", data: spec.data, ...(clustered ? { cluster: true, clusterRadius: 44, clusterMaxZoom: 7 } : {}) });
  const label = spec.labelProp ? ["to-string", ["coalesce", ["get", spec.labelProp], ""]] : null;
  const halo = { "text-halo-color": "#ffffff", "text-halo-width": 1.6 };

  const addClusters = () => {
    if (spec.subtle) {
      add({ id: id("cluster"), type: "circle", filter: ["has", "point_count"], paint: { "circle-color": spec.color, "circle-opacity": 0.28, "circle-stroke-color": spec.color, "circle-stroke-opacity": 0.5, "circle-stroke-width": 0.6, "circle-radius": ["step", ["get", "point_count"], 7, 10, 9, 40, 11] } }, true);
      add({ id: id("count"), type: "symbol", filter: ["has", "point_count"], layout: { "text-field": ["get", "point_count_abbreviated"], "text-font": FONT, "text-size": 9, "text-allow-overlap": true }, paint: { "text-color": spec.color, "text-opacity": 0.8 } });
      return;
    }
    add({ id: id("cluster"), type: "circle", filter: ["has", "point_count"], paint: { "circle-color": spec.color, "circle-opacity": 0.85, "circle-stroke-color": "#fff", "circle-stroke-width": 2, "circle-radius": ["step", ["get", "point_count"], 14, 10, 18, 40, 24] } }, true);
    add({ id: id("count"), type: "symbol", filter: ["has", "point_count"], layout: { "text-field": ["get", "point_count_abbreviated"], "text-font": FONT, "text-size": 12, "text-allow-overlap": true }, paint: { "text-color": "#ffffff" } });
  };
  const single = (...conds: unknown[]) => ["all", ...(clustered ? [["!", ["has", "point_count"]]] : []), ...conds];

  switch (spec.kind) {
    case "area":
      add({ id: id("fill"), type: "fill", filter: geom("Polygon"), paint: { "fill-color": spec.color, "fill-opacity": spec.soft ? 0.18 : 0.3 } }, true);
      add({ id: id("edge"), type: "line", filter: geom("Polygon"), paint: { "line-color": spec.color, "line-opacity": spec.soft ? 0.5 : 1, "line-width": spec.soft ? 0.8 : 1.6, ...(spec.dashed ? { "line-dasharray": [3, 2] } : {}) } });
      break;
    case "line":
      add({ id: id("line"), type: "line", filter: geom("LineString"), layout: { "line-cap": "round" }, paint: { "line-color": spec.color, "line-opacity": 0.9, "line-width": ["interpolate", ["linear"], ["zoom"], 2, 1.2, 8, 2.4], "line-dasharray": [2, 1.5] } }, true);
      add({ id: id("pt"), type: "circle", filter: geom("Point"), paint: { "circle-radius": 2.5, "circle-color": spec.color, "circle-stroke-color": "#fff", "circle-stroke-width": 1 } }, true);
      if (label) add({ id: id("label"), type: "symbol", filter: geom("Point"), minzoom: 3, layout: { "text-field": label, "text-font": FONT, "text-size": 11, "text-offset": [0, 0.9], "text-anchor": "top", "text-optional": true }, paint: { "text-color": "#0d2b2f", ...halo } });
      break;
    case "heat":
      // Detections folded into grid cells: `w` is the cell's weight (0..1), `f` its strongest reading in MW. A calm heat surface
      // far out, resolving into small dots (coloured by intensity) once the cells are far enough apart to read.
      add({ id: id("heat"), type: "heatmap", maxzoom: 8, paint: {
        "heatmap-weight": ["coalesce", ["get", "w"], 0.3],
        "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 0, 3, 3, 7, 6, 16, 8, 26],
        "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 0, 0.6, 6, 1.1, 8, 1.6],
        "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(224,86,27,0)", 0.2, "rgba(255,196,80,0.35)", 0.5, "rgba(240,130,40,0.7)", 0.85, "rgba(226,70,40,0.88)", 1, spec.color],
        "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 5.5, 0.9, 8, 0] } });
      add({ id: id("dots"), type: "circle", minzoom: 5.5, paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 5.5, 1.6, 9, 3.2, 12, 5],
        "circle-color": ["interpolate", ["linear"], ["coalesce", ["get", "f"], 0], 0, "#f2b84b", 40, "#ee7d2c", 150, spec.color],
        "circle-opacity": ["interpolate", ["linear"], ["zoom"], 5.5, 0, 7, 0.85],
        "circle-stroke-color": "rgba(255,255,255,0.7)", "circle-stroke-width": 0.5 } }, true);
      break;
    case "dots":
      if (clustered) addClusters();
      if (spec.halo) add({ id: id("halo"), type: "circle", paint: { "circle-radius": ["*", ["coalesce", ["get", "r"], 6], 2.1], "circle-color": spec.color, "circle-opacity": 0.14, "circle-stroke-color": spec.color, "circle-stroke-opacity": 0.35, "circle-stroke-width": 0.6 } });
      add({ id: id("dots"), type: "circle", ...(clustered ? { filter: ["!", ["has", "point_count"]] } : {}), paint: { "circle-radius": ["coalesce", ["get", "r"], 6], "circle-color": spec.color, "circle-opacity": 0.9, "circle-stroke-color": "#fff", "circle-stroke-width": spec.halo ? 0.8 : 1.5 } }, true);
      break;
    case "icons":
      spec.images?.(map);
      if (clustered) addClusters();
      add({ id: id("dot0"), type: "circle", filter: single(["<", ["get", "h"], 0]), paint: spec.subtle
        ? { "circle-radius": 2.5, "circle-color": ["get", "col"], "circle-opacity": 0.6, "circle-stroke-width": 0 }
        : { "circle-radius": 4, "circle-color": ["get", "col"], "circle-opacity": 0.9, "circle-stroke-color": "#fff", "circle-stroke-width": 0.8 } }, true);
      add({ id: id("icon"), type: "symbol", filter: single([">=", ["get", "h"], 0]), layout: {
        "icon-image": ["get", "ic"], "icon-rotate": ["get", "h"], "icon-rotation-alignment": "map", "icon-allow-overlap": true, "icon-ignore-placement": true,
        "icon-size": spec.subtle ? ["interpolate", ["linear"], ["zoom"], 3, 0.38, 7, 0.48, 14, 0.7] : ["interpolate", ["linear"], ["zoom"], 3, 0.6, 7, 0.75, 14, 1.1] },
        ...(spec.subtle ? { paint: { "icon-opacity": 0.65 } } : {}) }, true);
      break;
    case "assets": {
      // A status on record (ev > 0) draws larger and always carries its letter; a place that merely exists is a quiet dot whose letter
      // appears once the map is zoomed in. Data-driven only: a zoom expression cannot sit inside the property maths.
      add({ id: id("disc"), type: "circle", paint: {
        "circle-radius": ["coalesce", ["get", "r"], 5], "circle-color": ["get", "col"], "circle-opacity": ["coalesce", ["get", "op"], 1],
        "circle-stroke-color": "#ffffff", "circle-stroke-opacity": ["coalesce", ["get", "op"], 1],
        "circle-stroke-width": ["case", [">", ["coalesce", ["get", "ev"], 0], 0], 1.3, 0.6] } }, true);
      const letter = { "text-field": ["get", "g"], "text-font": FONT, "text-size": 10, "text-allow-overlap": true, "text-ignore-placement": true };
      const ink = { "text-color": "#ffffff", "text-opacity": ["coalesce", ["get", "op"], 1] };
      add({ id: id("g-ev"), type: "symbol", filter: [">", ["coalesce", ["get", "ev"], 0], 0], layout: letter, paint: ink });
      add({ id: id("g-all"), type: "symbol", minzoom: 5.5, filter: ["<=", ["coalesce", ["get", "ev"], 0], 0], layout: { ...letter, "text-size": 9 }, paint: ink });
      break;
    }
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
  if (info.href && /^\/[\w./-]*$/.test(info.href)) {
    const p = document.createElement("p");
    p.className = "lm-pop-src";
    const a = document.createElement("a");
    a.href = info.href;
    a.textContent = "Open the place page →";
    p.appendChild(a);
    root.appendChild(p);
  }
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
