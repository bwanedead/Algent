"use client";

// THE interactive map of the site: MapLibre GL JS over OpenFreeMap vector tiles, with our data drawn as GeoJSON layers
// (see mapLayers.ts). Every map on the site (daily theaters, dossiers, /live) goes through here.
//   - Loaded lazily: nothing is fetched until the figure nears the viewport (maplibre.ts pins the CDN build).
//   - Cooperative gestures: on a phone one finger scrolls the page and two move the map, so the map never traps scroll.
//   - While it loads, a neutral skeleton of the same size holds the place (never the static map: swapping one map for
//     another is a visible flash). `fallback` (our static SVG map) shows only when the interactive map cannot run:
//     no WebGL, the CDN/style fails (`onStatus("failed")` lets the caller swap in the full static figure), or no JS at all
//     (it is then rendered inside <noscript>).
//   - Keyboard: the map canvas takes arrow keys and +/-; `items` adds a button list that opens each mark's popup.
// Client-safe imports only (no lib/store). Basemap: docs/architecture/intel-desk.md "Maps".

/* eslint-disable @typescript-eslint/no-explicit-any -- MapLibre is loaded at runtime and untyped here */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { anchorOf, FIT_PADDING, type Bounds, type Feature, type LngLat, type Props } from "./geo";
import { installLayer, installSelected, inDrawOrder, popupNode, removeLayer, SELECTED_SOURCE, type LayerSpec } from "./mapLayers";
import { currentTheme, quietBasemap, STYLE_URL, TERRAIN_SOURCE } from "./mapStyle";
import { hasWebGL, loadMapLibre, styleReady } from "./maplibre";

import "./map.css";

export type MapStatus = "loading" | "ready" | "failed";
export type MapItem = { id: string; label: string };

type MapProps = {
  layers: LayerSpec[];
  /** The frame to show: [west, south, east, north] in degrees. */
  bounds: Bounds;
  /** Accessible name of the map. */
  label: string;
  /** Groups to hide (layer toggles live in the caller). */
  hidden?: string[];
  /** Stage shape (width / height) on wide screens; phones get a taller one. */
  aspect?: number;
  maxZoom?: number;
  /** Offer the 3D tilt button (pitch + free terrain tiles). */
  tilt?: boolean;
  /** The static map shown only when the interactive one cannot run (failed, no WebGL, no JS); never while it loads. */
  fallback?: ReactNode;
  /** The selected feature's `id` (highlighted and eased to). */
  selectedId?: string | null;
  onSelect?: (id: string | null, props: Props) => void;
  /** Keyboard/screen-reader route to every selectable mark. */
  items?: MapItem[];
  itemsLabel?: string;
  onStatus?: (s: MapStatus) => void;
  /** Our own data credit, under the map (the basemap's attribution is drawn on the map itself). */
  credit?: ReactNode;
  /** Frame something: `bounds` (fitted) or `center` + `zoom`; a new `nonce` re-triggers the move. */
  focus?: { nonce: number; bounds?: Bounds; center?: LngLat; zoom?: number } | null;
  /** Called with the live MapLibre map after every (re)sync of the style and layers (idempotent hook for extra layers), and with
   *  null when the map is torn down. */
  onMap?: (map: any | null) => void;
};

const LOAD_TIMEOUT_MS = 15000;
const reduceMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

function findFeature(layers: LayerSpec[], id: string): { f: Feature; spec: LayerSpec } | null {
  for (const spec of layers) {
    const f = spec.data.features.find((x) => x.properties.id === id);
    if (f) return { f, spec };
  }
  return null;
}

/** A touch-first device (phones, tablets): standard one-finger map gestures there. */
function isTouch(): boolean {
  if (typeof window === "undefined") return false;
  // Any touch capability counts (some phone browsers don't report a coarse pointer): a phone must never need two fingers.
  return (navigator.maxTouchPoints ?? 0) > 0 || "ontouchstart" in window || window.matchMedia?.("(pointer: coarse)").matches === true;
}

export default function LiveMap({ layers, bounds, label, hidden = [], aspect = 1.6, maxZoom = 9, tilt = false, fallback, selectedId = null, onSelect, items, itemsLabel = "Marked places", onStatus, credit, focus = null, onMap }: MapProps) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const popupRef = useRef<any>(null);
  const installed = useRef<{ spec: LayerSpec; all: string[] }[]>([]);
  const live = useRef({ layers, hidden, bounds, selectedId, onSelect, onMap, tilted: false });
  live.current = { ...live.current, layers, hidden, bounds, selectedId, onSelect, onMap };
  const [status, setStatus] = useState<MapStatus>("loading");
  const [armed, setArmed] = useState(false);
  const [tilted, setTilted] = useState(false);

  const report = useCallback((s: MapStatus) => {
    setStatus(s);
    onStatus?.(s);
  }, [onStatus]);

  const openPopup = useCallback((spec: LayerSpec | undefined, props: Props, at: LngLat) => {
    popupRef.current?.remove();
    const info = spec?.popup?.(props);
    const ml = (window as any).maplibregl;
    if (!info || !ml || !mapRef.current) return;
    popupRef.current = new ml.Popup({ maxWidth: "290px", offset: 14, closeButton: true, focusAfterOpen: false }).setLngLat(at).setDOMContent(popupNode(info)).addTo(mapRef.current);
  }, []);

  // (Re)build our sources and layers: on style load (first load, theme switch) and whenever the data changes.
  const sync = useCallback(() => {
    const map = mapRef.current;
    if (!map || !styleReady(map)) return;
    for (const { spec, all } of installed.current) removeLayer(map, spec, all);
    installed.current = [];
    if (map.getLayer(`${SELECTED_SOURCE}-ring`)) map.removeLayer(`${SELECTED_SOURCE}-ring`);
    if (map.getSource(SELECTED_SOURCE)) map.removeSource(SELECTED_SOURCE);
    const clickIds: string[] = [];
    const specOfLayer = new Map<string, LayerSpec>();
    for (const spec of inDrawOrder(live.current.layers)) {
      const { all, click } = installLayer(map, spec);
      installed.current.push({ spec, all });
      for (const id of click) {
        clickIds.push(id);
        specOfLayer.set(id, spec);
      }
    }
    installSelected(map);
    map.__lmClick = { clickIds, specOfLayer };
    applyHidden();
    applySelected(false);
    live.current.onMap?.(map);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function applyHidden() {
    const map = mapRef.current;
    if (!map) return;
    for (const { spec, all } of installed.current) {
      const vis = live.current.hidden.includes(spec.group) ? "none" : "visible";
      for (const id of all) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
    }
  }

  function applySelected(move: boolean) {
    const map = mapRef.current;
    const id = live.current.selectedId;
    const src = map?.getSource(SELECTED_SOURCE);
    if (!src) return;
    const hit = id ? findFeature(live.current.layers, id) : null;
    const at = hit ? anchorOf(hit.f) : null;
    src.setData({ type: "FeatureCollection", features: at ? [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: at } }] : [] });
    if (at && move) map.easeTo({ center: at, duration: reduceMotion() ? 0 : 500 });
  }

  // 1. Arm the map when the figure nears the viewport.
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setArmed(true);
      return;
    }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        setArmed(true);
        io.disconnect();
      }
    }, { rootMargin: "300px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // 2. Create the map once armed.
  useEffect(() => {
    if (!armed || !canvas.current) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    if (!hasWebGL()) {
      report("failed");
      return;
    }
    loadMapLibre().then((ml) => {
      if (cancelled || !canvas.current) return;
      const b = live.current.bounds;
      const map = new ml.Map({
        container: canvas.current,
        style: STYLE_URL[currentTheme()],
        bounds: b,
        fitBoundsOptions: { padding: FIT_PADDING, maxZoom },
        maxZoom: 14,
        // Touch: standard map gestures (one finger pans, double-tap and pinch zoom); the stage is shorter than the
        // screen so the page still scrolls past it. Desktop keeps Ctrl+wheel so wheel-scrolling the page isn't hijacked.
        cooperativeGestures: !isTouch(),
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
        attributionControl: false,
        fadeDuration: reduceMotion() ? 0 : 200,
      });
      mapRef.current = map;
      map.touchZoomRotate.disableRotation();
      map.addControl(new ml.NavigationControl({ showCompass: false }), "top-right");
      map.addControl(new ml.FullscreenControl(), "top-right");
      map.addControl(new ml.AttributionControl({ compact: false }), "bottom-right");
      map.getCanvas().setAttribute("aria-label", label);
      timer = setTimeout(() => {
        if (!cancelled && !map.loaded()) {
          map.remove();
          mapRef.current = null;
          report("failed");
        }
      }, LOAD_TIMEOUT_MS);
      map.on("style.load", () => {
        quietBasemap(map, currentTheme());
        sync();
        if (live.current.tilted) setTerrain(true);
      });
      map.once("load", () => {
        clearTimeout(timer);
        if (!cancelled) report("ready");
      });
      map.on("click", (e: any) => {
        const reg = map.__lmClick;
        if (!reg) return;
        const feats = map.queryRenderedFeatures(e.point, { layers: reg.clickIds.filter((id: string) => map.getLayer(id)) });
        const f = feats[0];
        if (!f) {
          popupRef.current?.remove();
          live.current.onSelect?.(null, {});
          return;
        }
        if (f.properties?.cluster) {
          const src = map.getSource(f.layer.source);
          src.getClusterExpansionZoom(f.properties.cluster_id).then((z: number) => map.easeTo({ center: f.geometry.coordinates, zoom: z + 0.5, duration: reduceMotion() ? 0 : 400 }));
          return;
        }
        const spec = reg.specOfLayer.get(f.layer.id) as LayerSpec | undefined;
        const props = f.properties as Props;
        openPopup(spec, props, f.geometry.type === "Point" ? f.geometry.coordinates : [e.lngLat.lng, e.lngLat.lat]);
        live.current.onSelect?.(typeof props.id === "string" ? props.id : null, props);
      });
      map.on("mousemove", (e: any) => {
        const reg = map.__lmClick;
        if (!reg) return;
        const ids = reg.clickIds.filter((id: string) => map.getLayer(id));
        map.getCanvas().style.cursor = ids.length && map.queryRenderedFeatures(e.point, { layers: ids }).length ? "pointer" : "";
      });
    }).catch(() => {
      if (!cancelled) report("failed");
    });
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      popupRef.current?.remove();
      live.current.onMap?.(null);
      mapRef.current?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [armed]);

  // 3. Follow the site theme (the basemap style is swapped; our layers are re-added on style.load).
  useEffect(() => {
    const mo = new MutationObserver(() => {
      const map = mapRef.current;
      if (map) map.setStyle(STYLE_URL[currentTheme()]);
    });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);

  useEffect(() => { sync(); }, [layers, sync]);
  useEffect(() => { applyHidden(); }, [hidden]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { applySelected(true); }, [selectedId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const map = mapRef.current;
    if (!focus || !map) return;
    const dur = reduceMotion() ? 0 : 700;
    if (focus.bounds) map.fitBounds(focus.bounds, { padding: FIT_PADDING, maxZoom: 11, duration: dur });
    else if (focus.center) map.easeTo({ center: focus.center, zoom: focus.zoom ?? map.getZoom(), duration: dur });
  }, [focus?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  function setTerrain(on: boolean) {
    const map = mapRef.current;
    if (!map) return;
    try {
      if (on) {
        if (!map.getSource("lm-dem")) map.addSource("lm-dem", TERRAIN_SOURCE);
        map.setTerrain({ source: "lm-dem", exaggeration: 1.5 });
      } else map.setTerrain(null);
    } catch {
      /* no terrain tiles: the tilt stays flat */
    }
  }

  const toggleTilt = () => {
    const map = mapRef.current;
    if (!map) return;
    const next = !tilted;
    live.current.tilted = next;
    setTilted(next);
    setTerrain(next);
    map.easeTo({ pitch: next ? 55 : 0, bearing: next ? -12 : 0, duration: reduceMotion() ? 0 : 700 });
  };
  const reset = () => mapRef.current?.fitBounds(bounds, { padding: FIT_PADDING, maxZoom, duration: reduceMotion() ? 0 : 500, pitch: 0, bearing: 0 });
  const pick = (id: string) => {
    const hit = findFeature(layers, id);
    if (!hit || !mapRef.current) return;
    const at = anchorOf(hit.f);
    mapRef.current.easeTo({ center: at, zoom: Math.max(mapRef.current.getZoom(), 5), duration: reduceMotion() ? 0 : 500 });
    openPopup(hit.spec, hit.f.properties, at);
    onSelect?.(id, hit.f.properties);
  };

  return (
    <div className={`lm lm-${status}`} ref={wrap} style={{ ["--lm-aspect" as string]: aspect }}>
      <div className="lm-stage">
        <div className="lm-canvas" ref={canvas} role="group" aria-label={label} />
        {status === "failed" && fallback && <div className="lm-fallback">{fallback}</div>}
        {status === "loading" && <div className="lm-skeleton" aria-hidden="true" />}
        {fallback && (
          <noscript>
            <style>{".lm-skeleton{display:none}"}</style>
            <div className="lm-fallback">{fallback}</div>
          </noscript>
        )}
        {status === "loading" && armed && <p className="lm-note" role="status">Loading the interactive map…</p>}
      </div>
      {status === "ready" && (
        <div className="lm-tools">
          <button type="button" className="lm-btn" onClick={reset}>Reset view</button>
          {tilt && (
            <button type="button" className="lm-btn" aria-pressed={tilted} onClick={toggleTilt}>
              3D tilt {tilted ? "on" : "off"}
            </button>
          )}
          <span className="lm-hint">{isTouch() ? "Drag to pan, pinch or double-tap to zoom; ⛶ for full screen." : "Drag to pan, Ctrl + scroll to zoom; arrow keys pan; ⛶ for full screen."}</span>
        </div>
      )}
      {status === "ready" && items && items.length > 0 && (
        <details className="lm-items">
          <summary>{itemsLabel} ({items.length})</summary>
          <ul>
            {items.map((it) => (
              <li key={it.id}>
                <button type="button" className="lm-item" onClick={() => pick(it.id)}>{it.label}</button>
              </li>
            ))}
          </ul>
        </details>
      )}
      {credit && <div className="lm-credit">{credit}</div>}
    </div>
  );
}
