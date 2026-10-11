// MapLibre GL JS, loaded at runtime from a pinned CDN build (like three.js in components/Scene3D.tsx): it is NOT an npm
// dependency, and nothing is fetched until a map scrolls into view. The library is a UMD bundle, so it is added with a
// <script> tag (it sets the `maplibregl` global) rather than imported. Client-safe: no server imports.

/* eslint-disable @typescript-eslint/no-explicit-any -- MapLibre is loaded at runtime and untyped here */

export const MAPLIBRE_VERSION = "4.7.1";
const JS_URL = `https://unpkg.com/maplibre-gl@${MAPLIBRE_VERSION}/dist/maplibre-gl.js`;
const CSS_URL = `https://unpkg.com/maplibre-gl@${MAPLIBRE_VERSION}/dist/maplibre-gl.css`;

let pending: Promise<any> | null = null;

/** True when this browser can create a WebGL context (MapLibre needs one). */
export function hasWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

/** The MapLibre namespace, loaded once per page. Rejects when the CDN is unreachable (callers fall back to the static map). */
export function loadMapLibre(): Promise<any> {
  const w = window as any;
  if (w.maplibregl) return Promise.resolve(w.maplibregl);
  if (pending) return pending;
  if (!document.querySelector("link[data-maplibre]")) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = CSS_URL;
    link.setAttribute("data-maplibre", "");
    document.head.appendChild(link);
  }
  pending = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = JS_URL;
    script.async = true;
    script.onload = () => (w.maplibregl ? resolve(w.maplibregl) : reject(new Error("maplibre-gl did not initialise")));
    script.onerror = () => reject(new Error("maplibre-gl failed to load"));
    document.head.appendChild(script);
  }).catch((e) => {
    pending = null; // a later map may retry
    throw e;
  });
  return pending;
}
