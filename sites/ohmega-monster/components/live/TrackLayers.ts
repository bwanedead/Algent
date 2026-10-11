// The moving layers of the /live map (ships, aircraft) as one MapLibre controller, kept apart from the declarative layers
// in components/map/mapLayers.ts because they are data-heavy and animated.
//
//   * Level of detail: far out the objects are a quiet density (heat); from DOT_ZOOM small dots; from ICON_ZOOM small icons
//     rotated to their heading, only for what is inside the (padded) view and capped at MAX_ICONS. GPU symbol layers do the drawing.
//   * Motion: between snapshots each icon is dead-reckoned along its heading at its speed (entities.reckon). The loop runs only
//     while the map is zoomed in, on screen, in a visible tab and without a reduced-motion preference.
//   * Tap an object: popup with what it broadcasts; the host is told (to load its trail). Trails are drawn from a line source.
//
// Client-only. MapLibre arrives as a runtime global (components/map/maplibre.ts), hence the untyped map.

/* eslint-disable @typescript-eslint/no-explicit-any -- MapLibre is loaded at runtime and untyped here */

import { popupNode } from "@/components/map/mapLayers";

import { colorOf, describe, iconOf, isNotable, passes, reckon, SHIP_CLASSES, NO_FILTER, type Entity, type EntityFilter, type Kind } from "./entities";
import type { Trail } from "./trails";
import { styleReady } from "@/components/map/maplibre";

export const DOT_ZOOM = 4;
export const ICON_ZOOM = 6.5;
const MAX_ICONS = 4500;
const PAD = 0.25;
const KINDS: Kind[] = ["ship", "air"];
const GROUP_COLOR: Record<Kind, string> = { ship: "#3fb0a8", air: "#8b6fd6" };
const EMPTY = { type: "FeatureCollection", features: [] as any[] };
const SOURCE: Record<Kind, { name: string; url: string }> = {
  ship: { name: "aisstream.io", url: "https://aisstream.io/" },
  air: { name: "adsb.lol", url: "https://adsb.lol/" },
};

const src = (k: Kind) => `lt-${k}`;
const layerIds = (k: Kind) => [`${src(k)}-heat`, `${src(k)}-dot`, `${src(k)}-dot0`, `${src(k)}-icon`, `${src(k)}-note`];
const CLICKABLE = (k: Kind) => [`${src(k)}-icon`, `${src(k)}-dot`, `${src(k)}-dot0`];
const reduceMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

function icon(draw: (c: CanvasRenderingContext2D, r: number) => void, size = 36): ImageData {
  const cv = document.createElement("canvas");
  cv.width = cv.height = size;
  const ctx = cv.getContext("2d") as CanvasRenderingContext2D;
  ctx.translate(size / 2, size / 2);
  draw(ctx, size * 0.42);
  return ctx.getImageData(0, 0, size, size);
}

function poly(ctx: CanvasRenderingContext2D, r: number, pts: [number, number][], fill: string) {
  ctx.beginPath();
  pts.forEach(([x, y], i) => (i ? ctx.lineTo(x * r, y * r) : ctx.moveTo(x * r, y * r)));
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.lineWidth = 1.6;
  ctx.strokeStyle = "rgba(255,255,255,0.92)";
  ctx.lineJoin = "round";
  ctx.stroke();
  ctx.fill();
}

const SHIP_SHAPE: [number, number][] = [[0, -1], [0.55, 0.85], [0, 0.45], [-0.55, 0.85]];
const PLANE_SHAPE: [number, number][] = [[0, -1], [0.12, -0.3], [0.95, 0.25], [0.95, 0.42], [0.12, 0.15], [0.1, 0.7], [0.42, 0.9], [0.42, 1], [0, 0.9], [-0.42, 1], [-0.42, 0.9], [-0.1, 0.7], [-0.12, 0.15], [-0.95, 0.42], [-0.95, 0.25], [-0.12, -0.3]];

export class Tracks {
  private map: any = null;
  private ents: Record<Kind, Entity[]> = { ship: [], air: [] };
  private byId: Record<Kind, Map<number, Entity>> = { ship: new Map(), air: new Map() };
  private filter: EntityFilter = NO_FILTER;
  private on: Record<Kind, boolean> = { ship: true, air: true };
  private trails: Trail[] = [];
  private selected: Entity | null = null;
  private popup: any = null;
  private raf = 0;
  private last = 0;
  private visible = true;
  private io: IntersectionObserver | null = null;
  private bound = new WeakSet<object>();
  /** Set by the host: called (after the icons are rebuilt) whenever the view stops moving. */
  onView: (() => void) | null = null;

  constructor(private onSelect: (e: Entity | null) => void) {}

  // ---- wiring -----------------------------------------------------------------------------------------------------------
  /** Called after every style load (first load, theme switch) and layer sync: (re)creates sources, layers and icons, idempotently. */
  attach(map: any) {
    this.map = map;
    this.addIcons();
    for (const k of KINDS) this.addGroup(k);
    if (!map.getSource("lt-trails")) {
      map.addSource("lt-trails", { type: "geojson", data: EMPTY });
      map.addLayer({ id: "lt-trails-line", source: "lt-trails", type: "line", layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": ["get", "col"], "line-width": 1.6, "line-opacity": 0.75 } });
      map.addSource("lt-sel", { type: "geojson", data: EMPTY });
      map.addLayer({ id: "lt-sel-ring", source: "lt-sel", type: "circle", paint: { "circle-radius": 14, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
    }
    for (const id of ["lt-trails-line", ...KINDS.flatMap(layerIds), "lt-sel-ring"]) if (map.getLayer(id)) map.moveLayer(id); // keep above the declarative layers
    if (!this.bound.has(map)) {
      this.bound.add(map);
      this.bind(map);
    }
    this.rebuild();
    this.drawTrails();
    this.drawSelected();
    this.start();
  }

  detach() {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.io?.disconnect();
    this.io = null;
    this.popup?.remove();
    this.popup = null;
    this.map = null;
  }

  private bind(map: any) {
    const ids = KINDS.flatMap(CLICKABLE);
    map.on("click", (e: any) => {
      const live = ids.filter((id) => map.getLayer(id));
      const f = live.length ? map.queryRenderedFeatures(e.point, { layers: live })[0] : null;
      if (!f) return this.select(null);
      const kind: Kind = f.properties.k === "s" ? "ship" : "air";
      this.select(this.byId[kind].get(Number(f.properties.id)) ?? null);
    });
    map.on("mousemove", (e: any) => {
      const live = ids.filter((id) => map.getLayer(id));
      if (live.length) map.getCanvas().style.cursor = map.queryRenderedFeatures(e.point, { layers: live }).length ? "pointer" : "";
    });
    map.on("moveend", () => {
      this.rebuild();
      this.onView?.();
    });
    this.io?.disconnect();
    if (typeof IntersectionObserver !== "undefined") {
      this.io = new IntersectionObserver((entries) => (this.visible = entries.some((en) => en.isIntersecting)));
      this.io.observe(map.getContainer());
    }
  }

  private addIcons() {
    const map = this.map;
    const put = (name: string, data: ImageData) => {
      if (!map.hasImage(name)) map.addImage(name, data, { pixelRatio: 2 });
    };
    SHIP_CLASSES.forEach((c, i) => put(`lt-ship-${i}`, icon((ctx, r) => poly(ctx, r, SHIP_SHAPE, c.color))));
    put("lt-air-civil", icon((ctx, r) => poly(ctx, r, PLANE_SHAPE, "#8fa3b5")));
    put("lt-air-mil", icon((ctx, r) => poly(ctx, r, PLANE_SHAPE, "#8b6fd6")));
  }

  private addGroup(k: Kind) {
    const map = this.map;
    if (map.getSource(src(k))) return;
    const s = src(k);
    const col = GROUP_COLOR[k];
    map.addSource(s, { type: "geojson", data: EMPTY });
    map.addLayer({ id: `${s}-heat`, source: s, type: "heatmap", maxzoom: DOT_ZOOM + 1, paint: {
      "heatmap-weight": 1,
      "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 0, 5, 2, 9, 5, 16],
      "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 0, 0.5, 5, 1.2],
      "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.2, `${col}33`, 0.6, `${col}99`, 1, col],
      "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], DOT_ZOOM, 0.85, DOT_ZOOM + 1, 0] } });
    const dotPaint = { "circle-color": ["get", "col"], "circle-opacity": 0.85, "circle-stroke-width": 0.5, "circle-stroke-color": "rgba(255,255,255,0.7)" };
    map.addLayer({ id: `${s}-dot`, source: s, type: "circle", minzoom: DOT_ZOOM, maxzoom: ICON_ZOOM, paint: { ...dotPaint,
      "circle-radius": ["interpolate", ["linear"], ["zoom"], DOT_ZOOM, 1.3, ICON_ZOOM, 2.4] } });
    map.addLayer({ id: `${s}-dot0`, source: s, type: "circle", minzoom: ICON_ZOOM, filter: ["<", ["get", "h"], 0], paint: { ...dotPaint, "circle-radius": 3 } });
    map.addLayer({ id: `${s}-icon`, source: s, type: "symbol", minzoom: ICON_ZOOM, filter: [">=", ["get", "h"], 0], layout: {
      "icon-image": ["get", "ic"], "icon-rotate": ["get", "h"], "icon-rotation-alignment": "map", "icon-allow-overlap": true, "icon-ignore-placement": true,
      "icon-size": ["interpolate", ["linear"], ["zoom"], ICON_ZOOM, 0.5, 10, 0.8, 14, 1.1] } });
    map.addLayer({ id: `${s}-note`, source: s, type: "circle", minzoom: DOT_ZOOM + 1, filter: ["==", ["get", "n"], 1], paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], DOT_ZOOM + 1, 5, 12, 11], "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#ffd166", "circle-stroke-width": 1.2, "circle-opacity": 0.9 } });
  }

  // ---- data -------------------------------------------------------------------------------------------------------------
  setEntities(kind: Kind, ents: Entity[]) {
    this.ents[kind] = ents;
    this.byId[kind] = new Map(ents.map((e) => [e.id, e]));
    this.rebuild(kind);
  }

  entities(kind: Kind): Entity[] {
    return this.ents[kind];
  }

  setFilter(f: EntityFilter, on: Record<Kind, boolean>) {
    this.filter = f;
    this.on = on;
    this.rebuild();
  }

  setTrails(trails: Trail[]) {
    this.trails = trails;
    this.drawTrails();
  }

  /** Objects inside the current view (for "trails for visible"), selected and notable first. */
  visibleEntities(): Entity[] {
    const b = this.map?.getBounds();
    if (!b || this.map.getZoom() < DOT_ZOOM + 1) return []; // far out a trail per object is a hairball, not information
    const out: Entity[] = [];
    for (const k of KINDS) {
      if (!this.on[k]) continue;
      for (const e of this.ents[k]) if (e.lon >= b.getWest() && e.lon <= b.getEast() && e.lat >= b.getSouth() && e.lat <= b.getNorth() && passes(e, this.filter)) out.push(e);
    }
    return out.sort((a, c) => Number(c === this.selected) - Number(a === this.selected) || Number(isNotable(c)) - Number(isNotable(a)) || c.spd - a.spd);
  }

  position(e: Entity): [number, number] {
    return reckon(e, Date.now() / 1000);
  }

  flyTo(e: Entity, zoom = 9) {
    if (!this.map) return;
    this.map.easeTo({ center: this.position(e), zoom: Math.max(this.map.getZoom(), zoom), duration: reduceMotion() ? 0 : 600 });
  }

  select(e: Entity | null, open = true) {
    this.popup?.remove();
    this.popup = null;
    this.selected = e;
    if (e && open) {
      const ml = (window as any).maplibregl;
      const d = describe(e, Date.now() / 1000);
      if (ml && this.map) {
        this.popup = new ml.Popup({ maxWidth: "270px", offset: 12, closeButton: true, focusAfterOpen: false })
          .setLngLat(this.position(e)).setDOMContent(popupNode({ kind: d.kind, title: d.title, lines: d.lines, source: SOURCE[e.kind].name, url: SOURCE[e.kind].url })).addTo(this.map);
        this.popup.on("close", () => {
          if (this.selected === e) {
            this.selected = null;
            this.drawSelected();
            this.onSelect(null);
          }
        });
      }
    }
    this.drawSelected();
    this.onSelect(e);
  }

  // ---- drawing ----------------------------------------------------------------------------------------------------------
  private rebuild(only?: Kind) {
    const map = this.map;
    if (!map || !styleReady(map)) return;
    const z = map.getZoom();
    const detail = z >= ICON_ZOOM;
    const now = Date.now() / 1000;
    const b = detail ? map.getBounds() : null;
    for (const k of only ? [only] : KINDS) {
      const s = map.getSource(src(k));
      if (!s) continue;
      if (!this.on[k]) {
        s.setData(EMPTY);
        continue;
      }
      let list = this.ents[k].filter((e) => passes(e, this.filter));
      if (b) {
        const dx = (b.getEast() - b.getWest()) * PAD;
        const dy = (b.getNorth() - b.getSouth()) * PAD;
        list = list.filter((e) => e.lon >= b.getWest() - dx && e.lon <= b.getEast() + dx && e.lat >= b.getSouth() - dy && e.lat <= b.getNorth() + dy);
        if (list.length > MAX_ICONS) {
          const keep = list.filter((e) => isNotable(e) || e === this.selected);
          const rest = list.filter((e) => !(isNotable(e) || e === this.selected));
          const stride = Math.ceil(rest.length / Math.max(1, MAX_ICONS - keep.length));
          list = [...keep, ...rest.filter((_, i) => i % stride === 0)];
        }
      }
      s.setData({ type: "FeatureCollection", features: list.map((e) => ({
        type: "Feature",
        properties: { id: e.id, k: e.kind === "ship" ? "s" : "a", h: e.hdg, ic: iconOf(e), col: colorOf(e), n: isNotable(e) ? 1 : 0 },
        geometry: { type: "Point", coordinates: detail ? reckon(e, now) : [e.lon, e.lat] } })) });
    }
    if (this.selected) this.drawSelected();
  }

  private drawTrails() {
    const s = this.map?.getSource("lt-trails");
    if (!s) return;
    s.setData({ type: "FeatureCollection", features: this.trails.map((t) => {
      const coordinates: number[][] = [];
      for (let i = 0; i + 1 < t.pts.length; i += 2) coordinates.push([t.pts[i], t.pts[i + 1]]);
      return { type: "Feature", properties: { col: t.col }, geometry: { type: "LineString", coordinates } };
    }) });
  }

  private drawSelected() {
    const s = this.map?.getSource("lt-sel");
    if (!s) return;
    s.setData({ type: "FeatureCollection", features: this.selected ? [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: this.position(this.selected) } }] : [] });
  }

  // ---- motion -----------------------------------------------------------------------------------------------------------
  private start() {
    if (this.raf || reduceMotion()) return;
    const tick = (t: number) => {
      this.raf = requestAnimationFrame(tick);
      const map = this.map;
      if (!map || document.hidden || !this.visible || map.isMoving()) return;
      const z = map.getZoom();
      if (z < ICON_ZOOM || t - this.last < (z >= 10 ? 250 : z >= 8 ? 500 : 1000)) return;
      this.last = t;
      this.rebuild();
    };
    this.raf = requestAnimationFrame(tick);
  }
}
