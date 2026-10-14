"use client";

// THE interactive map of the site: MapLibre GL JS over OpenFreeMap vector tiles, with our data drawn as GeoJSON layers
// (see mapLayers.ts). Every map on the site (daily theaters, dossiers, /live) goes through here.
//   - Loaded lazily: nothing is fetched until the figure nears the viewport (maplibre.ts pins the CDN build).
//   - Gestures are Google Maps' on every device (wheel/trackpad zoom, drag pan with inertia, pinch, double-tap/click zoom, north-up
//     until the 3D tilt is on); the canvas takes touch-action: none (map.css), and the stage is shorter than a phone screen so the page
//     can still be scrolled past the map. Programmatic moves are one smooth flyTo ("Show me", headlines, picks).
//   - While it loads, a panel of the same size with the site's globe spinner holds the place (never the static map: swapping one map for
//     another is a visible flash). `fallback` (our static SVG map) shows only when the interactive map cannot run:
//     no WebGL, the CDN/style fails (`onStatus("failed")` lets the caller swap in the full static figure), or no JS at all
//     (it is then rendered inside <noscript>).
//   - Keyboard: the map canvas takes arrow keys and +/-; `items` adds a button list that opens each mark's popup.
// Client-safe imports only (no lib/store). Basemap: docs/architecture/intel-desk.md "Maps".

/* eslint-disable @typescript-eslint/no-explicit-any -- MapLibre is loaded at runtime and untyped here */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import GlobeSpinner from "@/components/GlobeSpinner";

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
  /** "Show me": fly to the feature whose `id` this is and open its popup (a new `nonce` re-triggers; also starts a not-yet-loaded map). */
  reveal?: { nonce: number; id: string } | null;
  /** How many zoom levels the user may go out beyond the framed view (the frame itself is never cropped). */
  zoomOutRoom?: number;
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

type ScrollMode = "auto" | "standard" | "reversed";
const SCROLL_KEY = "ohmega-map-scroll";
const SCROLL_LABEL: Record<ScrollMode, string> = { auto: "Scroll zoom: auto", standard: "Scroll zoom: standard", reversed: "Scroll zoom: reversed" };

function readScrollMode(): ScrollMode {
  try {
    const v = localStorage.getItem(SCROLL_KEY);
    return v === "standard" || v === "reversed" ? v : "auto";
  } catch {
    return "auto";
  }
}

/**
 * A touchpad's two-finger scroll arrives as small, smooth wheel deltas (pixels); a mouse wheel as coarse fixed steps (~100/120
 * per notch, or line mode). With "natural" scrolling a touchpad swipe up is reported as scroll DOWN, which every map library reads
 * as zoom out — backwards to the person swiping. Auto mode reverses touchpad scrolls; pinch (ctrlKey) is never touched.
 *
 * The decision must be STICKY: a fast swipe also emits a few large integer deltas mid-gesture, and judging each event alone
 * flips the zoom back and forth (flicker). So once a touchpad is seen we keep treating the device as one, and only fall back to
 * mouse after a clear, isolated wheel notch (a big round step that starts a new burst).
 */
const wheelState = { touchpad: false, lastAt: 0 };

function looksLikeTouchpad(e: WheelEvent): boolean {
  const now = performance.now();
  const gap = now - wheelState.lastAt;
  wheelState.lastAt = now;
  if (e.deltaMode !== 0) return (wheelState.touchpad = false);           // line/page mode: a mouse wheel
  const d = Math.abs(e.deltaY);
  if (d === 0) return wheelState.touchpad;
  const smooth = d < 40 || !Number.isInteger(e.deltaY);
  if (smooth) return (wheelState.touchpad = true);
  const notch = d >= 100 && (d % 100 === 0 || d % 120 === 0);
  if (notch && gap > 250) return (wheelState.touchpad = false);           // an isolated wheel notch: the mouse is back
  return wheelState.touchpad;                                              // mid-burst: keep the current verdict
}

/** A touch-first device (phones, tablets, iPads), for wording and tap sizes only: gestures need no switch, because MapLibre takes
 *  wheel and drag from a mouse and touches from a finger side by side (so a hybrid laptop gets both). iPadOS reports itself as a Mac
 *  ("MacIntel"), so a Mac with more than one touch point is an iPad; a plain pointer:coarse covers phones and Android tablets. */
function isTouch(): boolean {
  if (typeof window === "undefined") return false;
  const points = navigator.maxTouchPoints ?? 0;
  const ipad = /Mac/i.test(navigator.platform ?? "") && points > 1;
  const primaryCoarse = window.matchMedia?.("(pointer: coarse)").matches === true;
  return ipad || primaryCoarse || (points > 0 && window.matchMedia?.("(any-pointer: fine)").matches !== true);
}

/** Is this click a finger's tap (wider hit box)? The event says so when it can; otherwise the device class does. */
const tappedByFinger = (e: any) => e.originalEvent?.pointerType === "touch" || e.originalEvent?.type?.startsWith("touch") || isTouch();
const TAP_PX = 18; // half-width of the box searched around a finger's tap for a mark (a mouse gets MOUSE_PX)
const MOUSE_PX = 5;

/** A compass that exists only while the map is rotated: "reset north". */
function northControl(map: any) {
  const el = document.createElement("div");
  el.className = "maplibregl-ctrl maplibregl-ctrl-group lm-north";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "maplibregl-ctrl-compass";
  btn.setAttribute("aria-label", "Reset north");
  btn.title = "Reset north";
  btn.innerHTML = '<span class="maplibregl-ctrl-icon" aria-hidden="true"></span>';
  const icon = btn.firstElementChild as HTMLElement;
  btn.addEventListener("click", () => map.easeTo({ bearing: 0, duration: reduceMotion() ? 0 : 400 }));
  el.appendChild(btn);
  const show = () => {
    const b = map.getBearing();
    el.style.display = Math.abs(b) < 0.5 ? "none" : "";
    icon.style.transform = `rotate(${-b}deg)`;
  };
  map.on("rotate", show);
  show();
  return { onAdd: () => el, onRemove: () => { map.off("rotate", show); el.remove(); } };
}

export default function LiveMap({ layers, bounds, label, hidden = [], aspect = 1.6, maxZoom = 9, tilt = false, fallback, selectedId = null, onSelect, items, itemsLabel = "Marked places", onStatus, credit, focus = null, reveal = null, zoomOutRoom = 1.5, onMap }: MapProps) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const popupRef = useRef<any>(null);
  const installed = useRef<{ spec: LayerSpec; all: string[] }[]>([]);
  const live = useRef<{ layers: LayerSpec[]; hidden: string[]; bounds: Bounds; selectedId: string | null; onSelect: MapProps["onSelect"]; onMap: MapProps["onMap"]; tilted: boolean; fromMap: string | null; pending: { nonce: number; id: string } | null }>({ layers, hidden, bounds, selectedId, onSelect, onMap, tilted: false, fromMap: null, pending: null });
  live.current = { ...live.current, layers, hidden, bounds, selectedId, onSelect, onMap };
  const [status, setStatus] = useState<MapStatus>("loading");
  const [armed, setArmed] = useState(false);
  const [tilted, setTilted] = useState(false);
  const [scrollMode, setScrollMode] = useState<ScrollMode>("auto");
  const scrollModeRef = useRef<ScrollMode>("auto");
  useEffect(() => { const m = readScrollMode(); setScrollMode(m); scrollModeRef.current = m; }, []);

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
    runPending();
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
    if (at && move) fly(at);
  }

  /** A programmatic move: one smooth flight (a jump under reduced motion). `zoom` only ever zooms in. */
  function fly(at: LngLat, zoom?: number) {
    const map = mapRef.current;
    if (!map) return;
    const z = zoom === undefined ? map.getZoom() : Math.max(map.getZoom(), zoom);
    if (reduceMotion()) map.jumpTo({ center: at, zoom: z });
    else map.flyTo({ center: at, zoom: z, speed: 1.3, curve: 1.3, essential: true });
  }

  /** "Show me": fly to the feature and open its popup; held until the map and its layers exist. */
  function runPending() {
    const map = mapRef.current;
    const want = live.current.pending;
    if (!want || !map || !styleReady(map)) return;
    live.current.pending = null;
    const hit = findFeature(live.current.layers, want.id);
    if (!hit) return;
    const at = anchorOf(hit.f);
    fly(at, 6);
    openPopup(hit.spec, hit.f.properties, at);
    live.current.fromMap = want.id;
    live.current.onSelect?.(want.id, hit.f.properties);
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
        // Google-Maps rules on every device, no cooperative-gesture gate: the wheel/trackpad zooms under the pointer, a drag pans
        // (with inertia), double-click/double-tap zooms in, pinch zooms, +/- and arrows work. MapLibre reads mouse and touch
        // separately, so a hybrid laptop gets both. The stage is shorter than the screen, so the page still scrolls past the map.
        // North stays up (no twist, no tilt-drag) until the 3D tilt toggle is on (toggleTilt).
        scrollZoom: true,
        dragPan: { linearity: 0.3, deceleration: 2500, maxSpeed: 1800 },
        doubleClickZoom: true,
        keyboard: true,
        renderWorldCopies: false,
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
        attributionControl: false,
        fadeDuration: reduceMotion() ? 0 : 200,
      });
      mapRef.current = map;
      // Reverse scroll-zoom where wanted (see looksLikeTouchpad): swallow the original wheel event in the capture phase and
      // re-dispatch a mirrored one, so MapLibre's own smooth wheel zoom still does the work.
      const wheelHost = map.getCanvasContainer();
      wheelHost.addEventListener("wheel", (e: WheelEvent) => {
        if ((e as any).__ohMirrored || e.ctrlKey) return;
        const mode = scrollModeRef.current;
        const flip = mode === "reversed" || (mode === "auto" && looksLikeTouchpad(e));
        if (!flip) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        const m = new WheelEvent("wheel", { deltaX: -e.deltaX, deltaY: -e.deltaY, deltaZ: e.deltaZ, deltaMode: e.deltaMode,
          clientX: e.clientX, clientY: e.clientY, screenX: e.screenX, screenY: e.screenY, shiftKey: e.shiftKey, altKey: e.altKey,
          metaKey: e.metaKey, bubbles: true, cancelable: true });
        (m as any).__ohMirrored = true;
        (e.target as Element).dispatchEvent(m);
      }, { capture: true, passive: false });
      map.touchZoomRotate.disableRotation();
      map.addControl(new ml.NavigationControl({ showCompass: false }), "top-right");
      map.addControl(northControl(map), "top-right");
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
        // The fitted frame is the widest view: allow some room beyond it, never less than the frame itself (a phone's world frame
        // sits below zoom 0, so a fixed floor would crop it).
        map.setMinZoom(Math.max(-2, map.getZoom() - zoomOutRoom));
        if (!cancelled) report("ready");
        runPending();
      });
      map.on("click", (e: any) => {
        const reg = map.__lmClick;
        if (!reg) return;
        const layerIds = reg.clickIds.filter((id: string) => map.getLayer(id));
        // Marks are small: a finger's tap searches a box (nearest point mark wins), a mouse a few pixels; exact hits first.
        let feats = map.queryRenderedFeatures(e.point, { layers: layerIds });
        if (!feats.length && layerIds.length) {
          const r = tappedByFinger(e) ? TAP_PX : MOUSE_PX;
          const near = map.queryRenderedFeatures([[e.point.x - r, e.point.y - r], [e.point.x + r, e.point.y + r]], { layers: layerIds });
          const dist = (g: any) => (g?.type === "Point" ? Math.hypot(map.project(g.coordinates).x - e.point.x, map.project(g.coordinates).y - e.point.y) : Infinity);
          feats = near.filter((x: any) => x.geometry?.type === "Point").sort((a: any, b: any) => dist(a.geometry) - dist(b.geometry));
        }
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
        // The popup is already at the mark: tell the host, but do not let its selection re-centre the map under the finger.
        live.current.fromMap = typeof props.id === "string" ? props.id : null;
        live.current.onSelect?.(live.current.fromMap, props);
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
  useEffect(() => {
    const fromMap = live.current.fromMap === selectedId; // chosen by tapping the map itself: it is already where it should be
    live.current.fromMap = null;
    applySelected(!fromMap);
  }, [selectedId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const map = mapRef.current;
    if (!focus || !map) return;
    const dur = reduceMotion() ? 0 : 700;
    if (focus.bounds) map.fitBounds(focus.bounds, { padding: FIT_PADDING, maxZoom: 11, duration: dur });
    else if (focus.center && reduceMotion()) map.jumpTo({ center: focus.center, zoom: focus.zoom ?? map.getZoom() });
    else if (focus.center) map.flyTo({ center: focus.center, zoom: focus.zoom ?? map.getZoom(), speed: 1.3, curve: 1.3, essential: true });
  }, [focus?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  // "Show me": arm a not-yet-loaded map, then fly + popup as soon as the map and its layers exist (runPending).
  useEffect(() => {
    if (!reveal) return;
    live.current.pending = reveal;
    setArmed(true);
    runPending();
  }, [reveal?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  // The box can change without a window resize (orientation change, the fullscreen control, the address bar sliding away on iOS):
  // keep the canvas matched to it.
  useEffect(() => {
    const el = canvas.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    let raf = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => mapRef.current?.resize());
    });
    ro.observe(el);
    const turned = () => setTimeout(() => mapRef.current?.resize(), 300); // iOS reports the new size a beat after the event
    window.addEventListener("orientationchange", turned);
    return () => { ro.disconnect(); cancelAnimationFrame(raf); window.removeEventListener("orientationchange", turned); };
  }, []);

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
    // Tilt on frees the view to turn (drag with the right button / two fingers, tilt with two-finger drag); off squares it back to north.
    const free = next ? "enable" : "disable";
    map.dragRotate[free]();
    map.touchPitch[free]();
    if (next) map.touchZoomRotate.enableRotation(); else map.touchZoomRotate.disableRotation();
    map.easeTo({ pitch: next ? 55 : 0, bearing: next ? -12 : 0, duration: reduceMotion() ? 0 : 700 });
  };
  const reset = () => mapRef.current?.fitBounds(bounds, { padding: FIT_PADDING, maxZoom, duration: reduceMotion() ? 0 : 500, pitch: 0, bearing: 0 });
  const pick = (id: string) => {
    const hit = findFeature(layers, id);
    if (!hit || !mapRef.current) return;
    const at = anchorOf(hit.f);
    fly(at, 5);
    openPopup(hit.spec, hit.f.properties, at);
    onSelect?.(id, hit.f.properties);
  };

  return (
    <div className={`lm lm-${status}`} ref={wrap} style={{ ["--lm-aspect" as string]: aspect }}>
      <div className="lm-stage">
        <div className="lm-canvas" ref={canvas} role="group" aria-label={label} />
        {status === "failed" && fallback && <div className="lm-fallback">{fallback}</div>}
        {status === "loading" && <div className="lm-skeleton">{armed && <GlobeSpinner size={96} caption="Loading the interactive map" />}</div>}
        {fallback && (
          <noscript>
            <style>{".lm-skeleton{display:none}"}</style>
            <div className="lm-fallback">{fallback}</div>
          </noscript>
        )}
      </div>
      {status === "ready" && (
        <div className="lm-tools">
          <button type="button" className="lm-btn" onClick={reset}>Reset view</button>
          <button type="button" className="lm-btn" title="Which way scrolling zooms. Auto reverses touchpad scrolls so swiping up zooms in."
            onClick={() => {
              const next: ScrollMode = scrollMode === "auto" ? "reversed" : scrollMode === "reversed" ? "standard" : "auto";
              setScrollMode(next);
              scrollModeRef.current = next;
              try { localStorage.setItem(SCROLL_KEY, next); } catch { /* storage blocked: applies for this visit */ }
            }}>{SCROLL_LABEL[scrollMode]}</button>
          {tilt && (
            <button type="button" className="lm-btn" aria-pressed={tilted} onClick={toggleTilt}>
              3D tilt {tilted ? "on" : "off"}
            </button>
          )}
          <span className="lm-hint">{isTouch() ? "Drag to pan, pinch or double-tap to zoom; ⛶ for full screen." : "Drag to pan, scroll or double-click to zoom; arrow keys pan, + and - zoom; ⛶ for full screen."}</span>
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
