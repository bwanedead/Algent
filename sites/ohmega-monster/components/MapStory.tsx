"use client";

// The map story (daily visual kind "mapstory" with a `spec`; contract: backend agents/intel/mapstory_spec.py): what moved
// where and when, played over the site's interactive map (LiveMap). A step is a date, a caption and the features that change;
// the reader presses play, scrubs, or steps. Routes draw themselves, points glide to their new place, areas and range rings
// fade in (map/storyFrame.ts holds the maths). It plays once when it first scrolls into view. Under prefers-reduced-motion
// there is no animation and no autoplay: previous/next and the scrubber jump from step to step. The step captions ARE the
// text alternative (listed under the map). If the interactive map cannot run, the server-drawn still takes its place.
// Client-safe imports only. The spec is fetched in the browser from our published assets.

/* eslint-disable @typescript-eslint/no-explicit-any -- MapLibre is loaded at runtime and untyped here */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { dateParts } from "@/components/timelineLayout";
import { parseMapStory, type MapStorySpec } from "@/lib/visualSpecs";

import type { Bounds } from "./map/geo";
import LiveMap, { type MapStatus } from "./map/LiveMap";
import { FONT, type LayerSpec } from "./map/mapLayers";
import { currentTheme } from "./map/mapStyle";
import { buildTimelines, frameAt, type Palette } from "./map/storyFrame";

import "./mapstory.css";

const STEP_MS = 1500; // time to travel one step at the natural pace
const MAX_JUMP_MS = 1300; // a scrub across many steps still lands within this
const HOLD_MS = 1300; // rest on each step while playing, so the caption can be read

// Map-local data colours (like the other maps): one set per basemap theme.
const PALETTE: Record<"paper" | "dark", Palette> = {
  paper: { ink: "#1f2933", accent: "#c2410c", warn: "#d98e04", cool: "#1d6fa5", hot: "#c8321e", good: "#2f7a46" },
  dark: { ink: "#e5e7eb", accent: "#f0a33a", warn: "#f0b429", cool: "#5aa9d6", hot: "#ff6b4a", good: "#6fbf7f" },
};

const SOURCES = ["ms-poly", "ms-line", "ms-pt", "ms-lbl"] as const;
const EMPTY = { type: "FeatureCollection", features: [] };
const calm = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const NO_LAYERS: LayerSpec[] = []; // our layers are added by hand (onMap), so LiveMap has none of its own

/** Add our sources and layers if the style does not have them (a theme switch swaps the style and drops them). */
function install(map: any) {
  if (map.getSource("ms-poly")) return;
  const dark = currentTheme() === "dark";
  for (const id of SOURCES) map.addSource(id, { type: "geojson", data: EMPTY });
  const color = ["get", "color"];
  const op = ["get", "op"];
  map.addLayer({ id: "ms-poly-fill", source: "ms-poly", type: "fill", paint: { "fill-color": color, "fill-opacity": ["*", op, ["get", "fa"]] } });
  map.addLayer({ id: "ms-poly-edge", source: "ms-poly", type: "line", filter: ["==", ["get", "kind"], "area"], paint: { "line-color": color, "line-opacity": op, "line-width": 1.8 } });
  map.addLayer({ id: "ms-poly-range", source: "ms-poly", type: "line", filter: ["==", ["get", "kind"], "range"], paint: { "line-color": color, "line-opacity": op, "line-width": 1.6, "line-dasharray": [3, 2] } });
  map.addLayer({ id: "ms-line", source: "ms-line", type: "line", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": color, "line-opacity": op, "line-width": ["interpolate", ["linear"], ["zoom"], 2, 2, 8, 4] } });
  map.addLayer({ id: "ms-pt", source: "ms-pt", type: "circle", paint: { "circle-radius": ["get", "r"], "circle-color": color, "circle-opacity": op, "circle-stroke-color": dark ? "#0c0f0e" : "#ffffff", "circle-stroke-width": 1.5, "circle-stroke-opacity": op } });
  map.addLayer({
    id: "ms-lbl", source: "ms-lbl", type: "symbol",
    layout: { "text-field": ["get", "text"], "text-font": FONT, "text-size": 12, "text-offset": [0, 0.9], "text-anchor": "top", "text-optional": true, "text-max-width": 9 },
    paint: { "text-color": dark ? "#e8e6df" : "#0d2b2f", "text-halo-color": dark ? "#0c0f0e" : "#ffffff", "text-halo-width": 1.6, "text-opacity": ["get", "op"] },
  });
}

function boundsOf(spec: MapStorySpec): Bounds {
  if (spec.bounds) return spec.bounds;
  const pts = spec.steps.flatMap((s) => s.show.flatMap((f) => (f.type === "point" || f.type === "range" ? [f.at] : f.type === "route" ? f.path : f.ring)));
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const [w, e, s, n] = pts.length ? [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)] : [-10, 10, -10, 10];
  return [w - 1, s - 1, e + 1, n + 1];
}

const fmtDate = (iso: string) => {
  const d = dateParts(iso);
  return `${d.weekday} ${d.day} ${d.year}`;
};

function Story({ spec, still }: { spec: MapStorySpec; still: ReactNode }) {
  const n = spec.steps.length;
  const bounds = useMemo(() => boundsOf(spec), [spec]);
  const timelines = useMemo(() => buildTimelines(spec), [spec]);
  const head = (bounds[3] - bounds[1]) * 0.05;
  const [status, setStatus] = useState<MapStatus>("loading");
  const [step, setStep] = useState(0); // the step shown and travelled to (the caption follows it)
  const [playing, setPlaying] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const pos = useRef(0);
  const target = useRef(0);
  const isPlaying = useRef(false);
  const hold = useRef(0);
  const last = useRef(0);
  const raf = useRef(0);
  const autoplayed = useRef(false);
  const still_ = useRef(calm());

  const draw = useCallback(() => {
    const map = mapRef.current;
    if (!map || !map.getSource("ms-poly")) return;
    const f = frameAt(timelines, pos.current, PALETTE[currentTheme()], head);
    map.getSource("ms-poly").setData(f.poly);
    map.getSource("ms-line").setData(f.line);
    map.getSource("ms-pt").setData(f.pt);
    map.getSource("ms-lbl").setData(f.lbl);
  }, [timelines, head]);

  const onMap = useCallback((map: any | null) => {
    mapRef.current = map;
    if (map) {
      install(map);
      draw();
    }
  }, [draw]);

  const tick = useCallback((t: number) => {
    const dt = last.current ? Math.min(64, t - last.current) : 16;
    last.current = t;
    const dist = target.current - pos.current;
    const moving = dist !== 0;
    if (moving) {
      const amt = Math.max(1 / STEP_MS, Math.abs(dist) / MAX_JUMP_MS) * dt;
      pos.current = Math.abs(dist) <= amt ? target.current : pos.current + Math.sign(dist) * amt;
    }
    draw();
    if (!moving && isPlaying.current) {
      if (hold.current === 0) hold.current = t + HOLD_MS;
      else if (t >= hold.current) {
        hold.current = 0;
        if (target.current < n - 1) {
          target.current += 1;
          setStep(target.current);
        } else {
          isPlaying.current = false;
          setPlaying(false);
        }
      }
    }
    if (moving || isPlaying.current) raf.current = requestAnimationFrame(tick);
    else {
      raf.current = 0;
      last.current = 0;
    }
  }, [draw, n]);

  const kick = useCallback(() => {
    if (raf.current) return;
    last.current = 0;
    raf.current = requestAnimationFrame(tick);
  }, [tick]);

  const goTo = useCallback((i: number) => {
    const to = Math.min(n - 1, Math.max(0, i));
    isPlaying.current = false;
    setPlaying(false);
    hold.current = 0;
    target.current = to;
    setStep(to);
    if (still_.current) {
      pos.current = to;
      draw();
    } else kick();
  }, [n, draw, kick]);

  /** Play or pause. `auto` is the first, unprompted play: it rests on the opening step before moving on. */
  const play = useCallback((auto = false) => {
    if (still_.current) return;
    if (isPlaying.current) {
      isPlaying.current = false;
      setPlaying(false);
      return;
    }
    if (Math.round(pos.current) >= n - 1 && target.current >= n - 1) {
      pos.current = 0;
      target.current = 0;
      draw();
    }
    isPlaying.current = true;
    setPlaying(true);
    hold.current = 0;
    if (!auto) {
      target.current = Math.min(n - 1, Math.round(pos.current) + 1);
      setStep(target.current);
    }
    kick();
  }, [n, draw, kick]);

  useEffect(() => () => cancelAnimationFrame(raf.current), []);
  useEffect(() => { if (status === "ready") draw(); }, [status, draw]);

  // Play once, the first time the map is on screen and ready (never under reduced motion).
  useEffect(() => {
    const el = root.current;
    if (!el || status !== "ready" || autoplayed.current || still_.current) return;
    if (typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting) && !autoplayed.current) {
        autoplayed.current = true;
        io.disconnect();
        play(true);
      }
    }, { threshold: 0.6 });
    io.observe(el);
    return () => io.disconnect();
  }, [status, play]);

  const s = spec.steps[step];
  const failed = status === "failed";
  return (
    <div className="ms" ref={root}>
      <LiveMap layers={NO_LAYERS} bounds={bounds} label={`Animated map: ${spec.title || spec.caption}. The steps are listed below the map.`} aspect={1.45} maxZoom={9}
        onMap={onMap} onStatus={setStatus} fallback={still} />
      {!failed && (
        <div className="ms-bar">
          {!still_.current && (
            <button type="button" className="lm-btn ms-play" onClick={() => play()} aria-label={playing ? "Pause" : step >= n - 1 ? "Replay" : "Play"}>
              {playing ? "❚❚ Pause" : step >= n - 1 ? "↺ Replay" : "▶ Play"}
            </button>
          )}
          <button type="button" className="lm-btn" onClick={() => goTo(step - 1)} disabled={step <= 0} aria-label="Previous step">‹</button>
          <input className="ms-range" type="range" min={0} max={n - 1} step={1} value={step} onChange={(e) => goTo(Number(e.target.value))}
            aria-label="Step" aria-valuetext={`Step ${step + 1} of ${n}, ${fmtDate(s.date)}`} />
          <button type="button" className="lm-btn" onClick={() => goTo(step + 1)} disabled={step >= n - 1} aria-label="Next step">›</button>
          <span className="ms-count" aria-hidden="true">{step + 1} / {n}</span>
        </div>
      )}
      {!failed && (
        <div className="ms-step" aria-live={playing ? "off" : "polite"}>
          <p className="ms-date">{fmtDate(s.date)}</p>
          <p className="ms-cap">{s.caption}</p>
          {s.sources.length > 0 && (
            <p className="ms-src">
              {s.sources.map((x, i) => (x.url ? <a key={i} href={x.url} className="geo-src" target="_blank" rel="noopener noreferrer nofollow">{x.label} ↗</a> : <span key={i} className="geo-micro">{x.label}</span>))}
            </p>
          )}
        </div>
      )}
      <details className="ms-all" open={failed}>
        <summary>All {n} steps</summary>
        <ol>
          {spec.steps.map((x, i) => (
            <li key={i} className={i === step ? "is-on" : ""}>
              <button type="button" onClick={() => goTo(i)} disabled={failed}>
                <b>{fmtDate(x.date)}</b> {x.caption}
              </button>
            </li>
          ))}
        </ol>
      </details>
    </div>
  );
}

export default function MapStory({ src, preview, title, caption }: { src: string; preview: string; title: string; caption: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [go, setGo] = useState(false);
  const [spec, setSpec] = useState<MapStorySpec | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setGo(true);
      return;
    }
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) {
        setGo(true);
        io.disconnect();
      }
    }, { rootMargin: "400px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!go) return;
    let dead = false;
    fetch(src)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j) => {
        if (dead) return;
        const s = parseMapStory(j);
        if (s) setSpec(s);
        else setFailed(true);
      })
      .catch(() => !dead && setFailed(true));
    return () => {
      dead = true;
    };
  }, [go, src]);

  const still = preview ? <img className="ms-still" src={preview} alt={title || caption || "Map"} loading="lazy" /> : null;
  return <div className="ms-host" ref={host}>{spec ? <Story spec={spec} still={still} /> : failed ? still : <div className="ms-wait">{still}</div>}</div>;
}
