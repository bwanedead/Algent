"use client";

// The flow map (daily visual kind "flow" with a `spec`; contract: backend agents/intel/flow_spec.py): goods, energy, money,
// weapons or people moving between places, over the site's interactive map (LiveMap, our layers added through its `onMap` hook
// like MapStory). Each flow is a curved arc with particles moving along it from source to target; width is in proportion to
// the amount where a cited fact states one (flows without a figure share one width, never an invented one). When the facts
// hold a disruption, the buttons under the map step through it: the broken route turns red and dashed with a cross, and the
// reroute that takes over runs in green. Tap an arc (or its row in the list) for what a source says about it.
// Reduced motion: particles stand still along each arc. If the interactive map cannot run, the server-drawn still takes its place.
// Client-safe imports only. The spec is fetched in the browser from our published assets.

/* eslint-disable @typescript-eslint/no-explicit-any -- MapLibre is loaded at runtime and untyped here */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { dateParts } from "@/components/timelineLayout";
import { useSpec } from "@/components/useSpec";
import { parseFlow, type FlowRoute, type FlowSpec, type SpecSource } from "@/lib/visualSpecs";

import type { Bounds } from "./map/geo";
import { commodityTones, frameAt, states } from "./map/flowFrame";
import LiveMap, { type MapStatus } from "./map/LiveMap";
import { FONT, type LayerSpec } from "./map/mapLayers";
import { currentTheme } from "./map/mapStyle";
import { PALETTE } from "./map/storyPalette";

import "./nativeviz.css";

const SOURCES = ["fl-line", "fl-pt", "fl-dots", "fl-lbl", "fl-cut"] as const;
const EMPTY = { type: "FeatureCollection", features: [] };
const FRAME_MS = 33; // about 30 frames a second is plenty for drifting dots
const calm = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const NO_LAYERS: LayerSpec[] = []; // our layers are added by hand (onMap), so LiveMap has none of its own
const fmtDate = (iso: string) => {
  const d = dateParts(iso);
  return `${d.day} ${d.year}`;
};
const hostOf = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
};

/** Add our sources, layers and click handlers if the style does not have them (a theme switch drops the layers). */
function install(map: any, onPick: (id: string | null) => void) {
  if (map.getSource("fl-line")) return;
  const dark = currentTheme() === "dark";
  for (const id of SOURCES) map.addSource(id, { type: "geojson", data: EMPTY });
  const color = ["get", "color"];
  const op = ["get", "op"];
  const halo = dark ? "#0c0f0e" : "#ffffff";
  const round = { "line-cap": "round", "line-join": "round" };
  map.addLayer({ id: "fl-hit", source: "fl-line", type: "line", layout: round, paint: { "line-color": "#000000", "line-opacity": 0, "line-width": 20 } });
  map.addLayer({ id: "fl-run", source: "fl-line", type: "line", filter: ["!=", ["get", "state"], "cut"], layout: round, paint: { "line-color": color, "line-opacity": op, "line-width": ["get", "w"] } });
  map.addLayer({ id: "fl-cutline", source: "fl-line", type: "line", filter: ["==", ["get", "state"], "cut"], layout: { "line-cap": "butt" }, paint: { "line-color": color, "line-opacity": op, "line-width": ["get", "w"], "line-dasharray": [1.6, 1.4] } });
  map.addLayer({ id: "fl-dots", source: "fl-dots", type: "circle", paint: { "circle-radius": ["get", "r"], "circle-color": color, "circle-opacity": op, "circle-stroke-color": halo, "circle-stroke-width": 0.8, "circle-stroke-opacity": op } });
  map.addLayer({ id: "fl-cut", source: "fl-cut", type: "circle", paint: { "circle-radius": 8, "circle-color": halo, "circle-opacity": ["get", "op"], "circle-stroke-color": color, "circle-stroke-width": 2, "circle-stroke-opacity": ["get", "op"] } });
  map.addLayer({ id: "fl-cutx", source: "fl-cut", type: "symbol", layout: { "text-field": "×", "text-font": FONT, "text-size": 16, "text-allow-overlap": true }, paint: { "text-color": color, "text-opacity": ["get", "op"] } });
  map.addLayer({ id: "fl-pt", source: "fl-pt", type: "circle", paint: { "circle-radius": ["get", "r"], "circle-color": color, "circle-stroke-color": halo, "circle-stroke-width": 1.5 } });
  map.addLayer({
    id: "fl-lbl", source: "fl-lbl", type: "symbol",
    layout: { "text-field": ["get", "text"], "text-font": FONT, "text-size": 12, "text-offset": [0, 0.9], "text-anchor": "top", "text-optional": true, "text-max-width": 9 },
    paint: { "text-color": dark ? "#e8e6df" : "#0d2b2f", "text-halo-color": halo, "text-halo-width": 1.6 },
  });
  if (map.__flBound) return; // listeners belong to the map object and survive a style swap: bind them once
  map.__flBound = true;
  map.on("click", "fl-hit", (e: any) => onPick(e.features?.[0]?.properties?.id ?? null));
  map.on("mouseenter", "fl-hit", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "fl-hit", () => (map.getCanvas().style.cursor = ""));
}

function boundsOf(spec: FlowSpec): Bounds {
  if (spec.bounds) return spec.bounds;
  const xs = spec.places.map((p) => p.at[0]);
  const ys = spec.places.map((p) => p.at[1]);
  return [Math.min(...xs) - 2, Math.min(...ys) - 2, Math.max(...xs) + 2, Math.max(...ys) + 2];
}

function Sources({ sources }: { sources: SpecSource[] }) {
  if (sources.length === 0) return null;
  return (
    <p className="nv-src">
      {sources.map((s, i) =>
        s.url ? (
          <a key={i} href={s.url} className="geo-src" target="_blank" rel="noopener noreferrer nofollow">
            {s.label || hostOf(s.url)} ↗
          </a>
        ) : (
          <span key={i} className="geo-micro">
            {s.label}
          </span>
        ),
      )}
    </p>
  );
}

const amountText = (f: FlowRoute) => (f.amount > 0 ? `${f.amount.toLocaleString("en")} ${f.unit}${f.period ? ` ${f.period}` : ""}` : "");

function Flow({ spec, still }: { spec: FlowSpec; still: ReactNode }) {
  const bounds = useMemo(() => boundsOf(spec), [spec]);
  const place = useMemo(() => new Map(spec.places.map((p): [string, string] => [p.id, p.name])), [spec]);
  const tones = useMemo(() => commodityTones(spec), [spec]);
  const [status, setStatus] = useState<MapStatus>("loading");
  const [step, setStep] = useState(0); // how many disruptions have happened
  const [sel, setSel] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const raf = useRef(0);
  const lastDraw = useRef(0);
  const visible = useRef(true);
  const live = useRef({ step, sel }); // read by the animation loop and the map's click handler
  const motionless = useRef(calm());
  live.current = { step, sel };

  const draw = useCallback((ms: number) => {
    const map = mapRef.current;
    if (!map || !map.getSource("fl-line")) return;
    const f = frameAt(spec, live.current.step, ms, live.current.sel, PALETTE[currentTheme()], motionless.current);
    map.getSource("fl-line").setData(f.line);
    map.getSource("fl-pt").setData(f.pt);
    map.getSource("fl-dots").setData(f.dots);
    map.getSource("fl-lbl").setData(f.lbl);
    map.getSource("fl-cut").setData(f.cut);
  }, [spec]);

  const onPick = useCallback((id: string | null) => setSel((cur) => (cur === id ? null : id)), []);

  const onMap = useCallback((map: any | null) => {
    mapRef.current = map;
    if (map) {
      install(map, onPick);
      draw(performance.now());
    }
  }, [draw, onPick]);

  // Animate while the figure is on screen and the tab is showing; a still frame is drawn whenever the state changes.
  useEffect(() => {
    if (status !== "ready") return;
    draw(performance.now());
    if (motionless.current) return;
    const tick = (t: number) => {
      raf.current = requestAnimationFrame(tick);
      if (!visible.current || t - lastDraw.current < FRAME_MS) return;
      lastDraw.current = t;
      draw(t);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [status, draw, step, sel]);

  useEffect(() => {
    const el = root.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((es) => (visible.current = es.some((e) => e.isIntersecting)));
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const st = useMemo(() => states(spec, step), [spec, step]);
  const shown = spec.flows.filter((f) => st.get(f.id) !== "hidden");
  const picked = spec.flows.find((f) => f.id === sel);
  const now = step > 0 ? spec.disruptions[step - 1] : null;
  const failed = status === "failed";
  const kinds = Array.from(new Set(spec.flows.map((f) => f.commodity.toLowerCase())));
  const chip = (state: string) => (state === "cut" ? " is-cut" : state === "alt" ? " is-alt" : "");

  return (
    <div className="nf" ref={root}>
      <LiveMap layers={NO_LAYERS} bounds={bounds} label={`Flow map: ${spec.title || spec.caption}. The routes are listed below the map.`} aspect={1.45} maxZoom={9}
        onMap={onMap} onStatus={setStatus} fallback={still} />
      {!failed && (
        <ul className="nf-key" aria-label="Key">
          {kinds.map((k) => (
            <li key={k} className={`nf-t-${tones.get(k)}`}>
              <i aria-hidden="true" />
              {k}
            </li>
          ))}
          {spec.disruptions.length > 0 && (
            <>
              <li className="nf-t-hot"><i aria-hidden="true" />cut</li>
              <li className="nf-t-good"><i aria-hidden="true" />reroute</li>
            </>
          )}
        </ul>
      )}
      {!failed && spec.disruptions.length > 0 && (
        <div className="nf-steps" role="group" aria-label="What happens when a route breaks">
          <button type="button" className="nv-btn" aria-pressed={step === 0} onClick={() => setStep(0)}>
            Normally
          </button>
          {spec.disruptions.map((d, i) => (
            <button key={d.id || i} type="button" className="nv-btn" aria-pressed={step === i + 1} onClick={() => setStep(i + 1)}>
              {fmtDate(d.date)}
            </button>
          ))}
        </div>
      )}
      {!failed && (
        <div className="nv-detail" aria-live="polite">
          {picked ? (
            <>
              <p className="nv-head">
                {picked.commodity}: {place.get(picked.source)} → {place.get(picked.target)}
              </p>
              {amountText(picked) && <p className="nv-meta">{amountText(picked)}</p>}
              {picked.detail && <p className="nv-text">{picked.detail}</p>}
              <Sources sources={picked.sources} />
            </>
          ) : now ? (
            <>
              <p className="nv-head">{fmtDate(now.date)}</p>
              <p className="nv-text">{now.effect}</p>
              <Sources sources={now.sources} />
            </>
          ) : (
            <p className="nv-hint">{spec.caption || "Tap a route."}</p>
          )}
        </div>
      )}
      <details className="nv-all" open={failed}>
        <summary>All {shown.length} routes</summary>
        <ol>
          {shown.map((f) => (
            <li key={f.id} className={`${sel === f.id ? "is-on" : ""}${chip(st.get(f.id) ?? "run")}`}>
              <button type="button" onClick={() => onPick(f.id)} disabled={failed}>
                <b>{f.commodity}</b>: {place.get(f.source)} → {place.get(f.target)}
                {f.via.length ? ` via ${f.via.map((v) => place.get(v)).join(", ")}` : ""}
                {amountText(f) ? ` (${amountText(f)})` : ""}
                {st.get(f.id) === "cut" ? " — cut" : st.get(f.id) === "alt" ? " — reroute" : ""}
                {f.detail ? `. ${f.detail}` : ""}
              </button>
            </li>
          ))}
        </ol>
        {spec.disruptions.map((d, i) => (
          <p key={d.id || i} className="nv-text">
            <b>{fmtDate(d.date)}</b> {d.effect}
          </p>
        ))}
      </details>
    </div>
  );
}

export default function NativeFlow({ src, preview, title, caption }: { src: string; preview: string; title: string; caption: string }) {
  const { host, spec, failed } = useSpec(src, parseFlow);
  const still = preview ? <img className="nv-still" src={preview} alt={title || caption || "Flow map"} loading="lazy" /> : null;
  return <div className="nv-host" ref={host}>{spec ? <Flow spec={spec} still={still} /> : failed ? still : <div className="nv-wait">{still}</div>}</div>;
}
