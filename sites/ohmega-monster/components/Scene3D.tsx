"use client";

// Interactive 3D scene viewer (daily visual kind "scene3d"; contract: backend agents/intel/scene_spec.py).
// three.js is NOT an npm dependency: it is imported at runtime from a pinned CDN build, only once the figure
// scrolls into view. The scene is declarative JSON (no code), so nothing fetched is ever executed except the
// pinned library. Any failure (fetch, no WebGL, bad scene) falls back to the server-rendered still.
// Renders on demand (no animation loop), honours prefers-reduced-motion, and labels are DOM overlays.

import { useCallback, useEffect, useRef, useState } from "react";

import "./scene3d.css";

/* eslint-disable @typescript-eslint/no-explicit-any -- three.js is loaded at runtime and untyped here */

const THREE_URL = "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js";
const CONTROLS_URL = "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js";

type V3 = [number, number, number];
type Obj = {
  id: string; type: string; label?: string; color?: string; opacity?: number; pos?: V3; rot_z_deg?: number; label_dz?: number;
  size?: V3; radius?: number; radius_top?: number | null; height?: number; length?: number; depth?: number;
  profile?: [number, number][]; points?: V3[]; style?: string; to?: V3; heights?: number[][]; polygons?: [number, number][][];
};
type Frame = { date: string; note?: string; visible?: Record<string, boolean>; pos?: Record<string, V3>; color?: Record<string, string> };
export type SceneSpec = {
  title: string; caption: string; unit: string; schematic?: boolean; ground?: string | null; objects: Obj[];
  cameras?: { id: string; label: string; position: V3; target: V3 }[];
  timeline?: { frames: Frame[] } | null; scale_bar?: { length: number; label: string } | null; alt?: string;
};

// Palette tokens -> colours, per site theme. Tokens are the contract; hex lives only here.
const PAPER: Record<string, string> = { ink: "#242722", muted: "#8a8a80", paper: "#f0eee6", water: "#a9c7dd", land: "#d6cfbb", accent: "#b3361b", warn: "#d98e04", cool: "#2f6f9f", hot: "#c8321e", good: "#3d7a4a" };
const DARK: Record<string, string> = { ink: "#d3d0c8", muted: "#7c8580", paper: "#0c0f0e", water: "#17323f", land: "#2b3a33", accent: "#e8a33d", warn: "#f0b429", cool: "#5aa9d6", hot: "#ff6b4a", good: "#6fbf7f" };

const PHONE_MAX_PIXEL_RATIO = 2;
const ws = (v: V3): V3 => [v[0], v[2], -v[1]]; // scene (x east, y north, z up) -> three (x, y up, z south)

async function loadThree(): Promise<{ THREE: any; OrbitControls: any }> {
  const threeUrl: string = THREE_URL; // a variable, so neither TypeScript nor webpack tries to resolve it
  const THREE = await import(/* webpackIgnore: true */ threeUrl);
  // OrbitControls imports the bare specifier "three"; point it at the same pinned module via a blob (one three instance).
  const src = await (await fetch(CONTROLS_URL)).text();
  const blob = new Blob([src.replace(/from\s*['"]three['"]/g, `from "${threeUrl}"`)], { type: "text/javascript" });
  const blobUrl = URL.createObjectURL(blob);
  try {
    const mod = await import(/* webpackIgnore: true */ blobUrl);
    return { THREE, OrbitControls: mod.OrbitControls };
  } finally {
    URL.revokeObjectURL(blobUrl);
  }
}

function extentOf(s: SceneSpec): number {
  let r = 0;
  for (const o of s.objects) {
    const p = o.pos || [0, 0, 0];
    r = Math.max(r, Math.abs(p[0]) + (o.radius || (o.size ? o.size[0] / 2 : 0)), Math.abs(p[1]) + (o.radius || (o.size ? o.size[1] / 2 : 0)));
    for (const ring of o.polygons || []) for (const q of ring) r = Math.max(r, Math.abs(q[0]), Math.abs(q[1]));
    for (const q of o.points || []) r = Math.max(r, Math.abs(q[0]), Math.abs(q[1]));
    for (const q of o.profile && o.type === "extrude" ? o.profile : []) r = Math.max(r, Math.abs(p[0] + q[0]), Math.abs(p[1] + q[1]));
    if (o.to) r = Math.max(r, Math.abs(o.to[0]), Math.abs(o.to[1]));
  }
  return r || 1;
}

type Built = { group: any; byId: Map<string, any>; labels: { id: string; el: HTMLDivElement; at: V3; follow: boolean }[] };

function build(THREE: any, s: SceneSpec, pal: Record<string, string>, labelHost: HTMLElement, r: number): Built {
  const group = new THREE.Group();
  const byId = new Map<string, any>();
  const labels: Built["labels"] = [];
  const color = (o: Obj) => new THREE.Color(pal[o.color || "accent"] || pal.accent);
  const mat = (o: Obj, wire = false) =>
    new THREE.MeshStandardMaterial({ color: color(o), roughness: 0.75, metalness: 0.05, transparent: (o.opacity ?? 1) < 1, opacity: o.opacity ?? 1, wireframe: wire, side: THREE.DoubleSide });

  if (s.ground) {
    const g = new THREE.Mesh(new THREE.PlaneGeometry(r * 2.2, r * 2.2).rotateX(-Math.PI / 2), new THREE.MeshStandardMaterial({ color: new THREE.Color(pal[s.ground] || pal.water), roughness: 1 }));
    g.position.y = -r * 0.004;
    group.add(g);
  }
  for (const o of s.objects) {
    const p = (o.pos || [0, 0, 0]) as V3;
    const wp = ws(p);
    let m: any = null;
    switch (o.type) {
      case "box": {
        const z = o.size as V3;
        m = new THREE.Mesh(new THREE.BoxGeometry(z[0], z[2], z[1]).translate(0, z[2] / 2, 0), mat(o));
        break;
      }
      case "cylinder": {
        const h = o.height as number;
        m = new THREE.Mesh(new THREE.CylinderGeometry(o.radius_top ?? o.radius, o.radius, h, 28).translate(0, h / 2, 0), mat(o));
        break;
      }
      case "cone": {
        const h = o.height as number;
        m = new THREE.Mesh(new THREE.ConeGeometry(o.radius, h, 28).translate(0, h / 2, 0), mat(o));
        break;
      }
      case "sphere":
        m = new THREE.Mesh(new THREE.SphereGeometry(o.radius, 28, 18).translate(0, o.radius as number, 0), mat(o));
        break;
      case "capsule":
        m = new THREE.Mesh(new THREE.CapsuleGeometry(o.radius, o.length, 6, 18).rotateZ(Math.PI / 2).translate(0, o.radius as number, 0), mat(o));
        break;
      case "extrude": {
        const sh = new THREE.Shape((o.profile || []).map((q) => new THREE.Vector2(q[0], q[1])));
        m = new THREE.Mesh(new THREE.ExtrudeGeometry(sh, { depth: o.depth, bevelEnabled: false }).rotateX(-Math.PI / 2), mat(o));
        break;
      }
      case "lathe":
        m = new THREE.Mesh(new THREE.LatheGeometry((o.profile || []).map((q) => new THREE.Vector2(q[0], q[1])), 40), mat(o));
        break;
      case "line": {
        const pts = (o.points || []).map((q) => new THREE.Vector3(...ws(q)));
        const dashed = o.style === "dashed";
        const lm = dashed ? new THREE.LineDashedMaterial({ color: color(o), dashSize: r * 0.02, gapSize: r * 0.012 }) : new THREE.LineBasicMaterial({ color: color(o) });
        m = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), lm);
        if (dashed) m.computeLineDistances();
        break;
      }
      case "ring": {
        const pts = Array.from({ length: 129 }, (_, i) => new THREE.Vector3(Math.cos((i / 128) * Math.PI * 2) * (o.radius as number), 0, Math.sin((i / 128) * Math.PI * 2) * (o.radius as number)));
        m = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineDashedMaterial({ color: color(o), dashSize: r * 0.02, gapSize: r * 0.012 }));
        m.computeLineDistances();
        break;
      }
      case "arrow": {
        const to = new THREE.Vector3(...ws(o.to as V3));
        const from = new THREE.Vector3(...wp);
        const d = to.clone().sub(from);
        m = new THREE.ArrowHelper(d.clone().normalize(), new THREE.Vector3(0, 0, 0), d.length(), color(o).getHex(), r * 0.05, r * 0.025);
        break;
      }
      case "marker":
        m = new THREE.Mesh(new THREE.SphereGeometry(r * 0.014, 14, 10), new THREE.MeshBasicMaterial({ color: color(o) }));
        break;
      case "terrain": {
        const hs = o.heights || [];
        const sz = (o as any).size as unknown as [number, number];
        const rows = hs.length || 2, cols = hs.length ? hs[0].length : 2;
        const geo = new THREE.PlaneGeometry(sz[0], sz[1], cols - 1, rows - 1).rotateX(-Math.PI / 2);
        const pos = geo.attributes.position;
        for (let i = 0; i < pos.count; i++) pos.setY(i, hs.length ? hs[rows - 1 - Math.floor(i / cols)][i % cols] : 0); // row 0 = south
        geo.computeVertexNormals();
        m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: new THREE.Color(pal.land), roughness: 1, flatShading: true }));
        break;
      }
      case "coast": {
        const g = new THREE.Group();
        for (const ring of o.polygons || []) {
          const sh = new THREE.Shape(ring.map((q) => new THREE.Vector2(q[0], q[1])));
          g.add(new THREE.Mesh(new THREE.ExtrudeGeometry(sh, { depth: (o as any).height ?? 0.3, bevelEnabled: false }).rotateX(-Math.PI / 2), mat(o)));
        }
        m = g;
        break;
      }
      default:
        continue;
    }
    m.position.set(...wp);
    if (o.rot_z_deg) m.rotation.y = (o.rot_z_deg * Math.PI) / 180;
    group.add(m);
    byId.set(o.id, m);
    if (o.label) {
      const el = document.createElement("div");
      el.className = "s3d-label";
      el.textContent = o.label;
      labelHost.appendChild(el);
      const mid = o.type === "line" && o.points?.length ? o.points[Math.floor(o.points.length / 2)] : null; // a line is labelled mid-way
      const at: V3 = mid ? [p[0] + mid[0], p[1] + mid[1], p[2] + mid[2]] : p;
      labels.push({ id: o.id, el, at: [at[0], at[1], at[2] + (o.label_dz || 0)], follow: !mid });
    }
  }
  return { group, byId, labels };
}

export default function Scene3D({ src, preview, title, caption }: { src: string; preview?: string; title?: string; caption?: string }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [spec, setSpec] = useState<SceneSpec | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "failed">("idle");
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [cam, setCam] = useState("");
  const api = useRef<{ setFrame: (i: number) => void; setCamera: (id: string) => void } | null>(null);

  // Start only when scrolled into view (three.js is ~700 kB; most readers never open a scene).
  useEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setState("loading");
      return;
    }
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) {
        setState("loading");
        io.disconnect();
      }
    }, { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const go = state !== "idle";
  useEffect(() => {
    if (!go) return;
    let dead = false;
    let cleanup = () => {};
    (async () => {
      try {
        const [json, lib] = await Promise.all([fetch(src).then((r) => (r.ok ? r.json() : Promise.reject(new Error("scene " + r.status)))), loadThree()]);
        if (dead) return;
        const s = json as SceneSpec;
        if (!s || !Array.isArray(s.objects)) throw new Error("bad scene");
        cleanup = mount(lib, s, hostRef.current as HTMLDivElement, api);
        setSpec(s);
        setCam(s.cameras?.[0]?.id || "");
        setState("ready");
      } catch {
        if (!dead) setState("failed");
      }
    })();
    return () => {
      dead = true;
      cleanup();
    };
  }, [go, src]);

  const frames = spec?.timeline?.frames || [];
  useEffect(() => {
    api.current?.setFrame(frame);
  }, [frame]);
  useEffect(() => {
    if (!playing || frames.length < 2) return;
    const t = setInterval(() => setFrame((f) => Math.min(f + 1, frames.length - 1)), 1100);
    return () => clearInterval(t);
  }, [playing, frames.length]);
  useEffect(() => {
    if (playing && frames.length && frame >= frames.length - 1) setPlaying(false);
  }, [playing, frame, frames.length]);
  const pick = useCallback((id: string) => {
    setCam(id);
    api.current?.setCamera(id);
  }, []);

  if (state === "failed") {
    return preview ? (
      <div className="s3d">
        <img className="s3d-still" src={preview} alt={title || caption || "Scene"} />
        <p className="s3d-note">The interactive 3D view could not load here; this is a still of the scene.</p>
      </div>
    ) : (
      <p className="s3d-note">The interactive 3D view could not load here.</p>
    );
  }
  return (
    <div className="s3d">
      <div className="s3d-wrap">
        {/* the stage has no React children: mount() owns its DOM */}
        <div className="s3d-stage" ref={hostRef} tabIndex={0} role="group" aria-label={`Interactive 3D scene: ${title || caption || ""}. Drag to rotate, pinch or scroll to zoom, two fingers or right-drag to pan.`} />
        {state !== "ready" && (preview ? <img className="s3d-still s3d-cover" src={preview} alt="" loading="lazy" /> : <p className="s3d-note s3d-cover">Loading 3D scene…</p>)}
      </div>
      {state === "ready" && spec && (
        <>
          <div className="s3d-bar">
            {(spec.cameras || []).map((c) => (
              <button key={c.id} type="button" className={`s3d-btn${cam === c.id ? " is-on" : ""}`} onClick={() => pick(c.id)}>
                {c.label}
              </button>
            ))}
            <span className="s3d-hint">Drag to turn · scroll or pinch to zoom</span>
          </div>
          {frames.length >= 2 && (
            <div className="s3d-time">
              <button type="button" className="s3d-btn" onClick={() => {
                  if (!playing && frame + 1 >= frames.length) setFrame(0);
                  setPlaying((p) => !p);
                }}>
                {playing ? "Pause" : "Play"}
              </button>
              <input type="range" min={0} max={frames.length - 1} step={1} value={frame} aria-label="Date" onChange={(e) => {
                  setPlaying(false);
                  setFrame(Number(e.target.value));
                }} />
              <span className="s3d-date">
                {frames[frame].date}
                {frames[frame].note ? ` — ${frames[frame].note}` : ""}
              </span>
            </div>
          )}
          <details className="s3d-alt">
            <summary>Text description</summary>
            <p>{spec.alt || `${spec.title}. ${spec.caption}`}</p>
            <ul>
              {spec.objects.filter((o) => o.label).map((o) => (
                <li key={o.id}>{o.label}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </div>
  );
}

/** Build the renderer, controls and overlays inside `host`. Returns the teardown. */
function mount({ THREE, OrbitControls }: { THREE: any; OrbitControls: any }, s: SceneSpec, host: HTMLDivElement, api: { current: any }): () => void {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const light = document.documentElement.dataset.theme === "paper";
  const pal = light ? PAPER : DARK;
  const r = extentOf(s);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, PHONE_MAX_PIXEL_RATIO));
  renderer.setClearColor(new THREE.Color(pal.paper));
  host.replaceChildren();
  host.appendChild(renderer.domElement);
  renderer.domElement.className = "s3d-canvas";
  const overlay = document.createElement("div");
  overlay.className = "s3d-overlay";
  host.appendChild(overlay);

  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, new THREE.Color(pal.land), light ? 1.0 : 0.75));
  const sun = new THREE.DirectionalLight(0xffffff, light ? 1.1 : 0.8);
  sun.position.set(r, r * 1.5, r * 0.6);
  scene.add(sun);
  const built = build(THREE, s, pal, overlay, r);
  scene.add(built.group);

  const camera = new THREE.PerspectiveCamera(45, 1, r * 0.01, r * 30);
  const presets = s.cameras && s.cameras.length ? s.cameras : [{ id: "o", label: "Overview", position: [0, -1.4 * r, 0.9 * r] as V3, target: [0, 0, 0] as V3 }];
  const goto = (c: (typeof presets)[number]) => {
    camera.position.set(...ws(c.position));
    controls.target.set(...ws(c.target));
    controls.update();
  };
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = false; // render-on-demand: no loop needed
  controls.screenSpacePanning = true;
  controls.maxDistance = r * 12;
  controls.minDistance = r * 0.02;
  controls.maxPolarAngle = Math.PI * 0.495; // never under the ground
  controls.listenToKeyEvents(host);
  host.style.touchAction = "none";

  // scale bar (DOM): only drawn while its length is a sensible share of the width at the orbit target
  const bar = document.createElement("div");
  bar.className = "s3d-scale";
  const barLine = document.createElement("i");
  const barText = document.createElement("span");
  bar.append(barLine, barText);
  if (s.scale_bar) overlay.appendChild(bar);

  const frames = s.timeline?.frames || [];
  const visible = new Map<string, boolean>();
  const applyFrame = (i: number) => {
    if (!frames.length) return;
    for (const o of s.objects) {
      const m = built.byId.get(o.id);
      m?.position.set(...ws((o.pos || [0, 0, 0]) as V3));
      const col = new THREE.Color(pal[o.color || "accent"] || pal.accent);
      m?.traverse?.((n: any) => n.material?.color?.copy(col));
    }
    const vis = new Map<string, boolean>();
    for (let k = 0; k <= i; k++) {
      const f = frames[k];
      for (const [id, v] of Object.entries(f.visible || {})) vis.set(id, v);
      for (const [id, p] of Object.entries(f.pos || {})) built.byId.get(id)?.position.set(...ws(p));
      for (const [id, c] of Object.entries(f.color || {})) {
        const m = built.byId.get(id);
        const col = new THREE.Color(pal[c] || pal.accent);
        m?.traverse?.((n: any) => n.material?.color?.copy(col));
      }
    }
    visible.clear();
    vis.forEach((v, id) => visible.set(id, v));
    for (const [id, m] of built.byId) m.visible = visible.get(id) !== false;
    draw();
  };

  const v = new THREE.Vector3();
  function draw() {
    renderer.render(scene, camera);
    const w = host.clientWidth, h = host.clientHeight;
    for (const l of built.labels) {
      const m = built.byId.get(l.id);
      if (m && l.follow) v.set(m.position.x, m.position.y + (l.at[2] - ((s.objects.find((o) => o.id === l.id)?.pos?.[2]) || 0)), m.position.z);
      else v.set(...ws(l.at));
      v.project(camera);
      const show = (!m || m.visible) && v.z < 1 && Math.abs(v.x) < 1.05 && Math.abs(v.y) < 1.05;
      l.el.style.display = show ? "" : "none";
      if (show) l.el.style.transform = `translate(-50%,-100%) translate(${((v.x + 1) / 2) * w}px,${((1 - v.y) / 2) * h}px)`;
    }
    if (s.scale_bar) {
      const dist = camera.position.distanceTo(controls.target);
      const px = (s.scale_bar.length * (h / 2)) / (Math.tan((camera.fov * Math.PI) / 360) * dist);
      const ok = px >= 24 && px <= w * 0.6;
      bar.style.display = ok ? "" : "none";
      barLine.style.width = `${px}px`;
      barText.textContent = s.scale_bar.label;
    }
  }
  const resize = () => {
    const w = host.clientWidth, h = host.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    draw();
  };
  const ro = new ResizeObserver(resize);
  ro.observe(host);
  controls.addEventListener("change", draw);

  let raf = 0;
  api.current = {
    setFrame: applyFrame,
    setCamera: (id: string) => {
      const c = presets.find((p) => p.id === id);
      if (!c) return;
      if (reduced) return goto(c);
      const p0 = camera.position.clone(), t0 = controls.target.clone();
      const p1 = new THREE.Vector3(...ws(c.position)), t1 = new THREE.Vector3(...ws(c.target));
      const start = performance.now();
      cancelAnimationFrame(raf);
      const step = (now: number) => {
        const k = Math.min(1, (now - start) / 450), e = k * k * (3 - 2 * k);
        camera.position.lerpVectors(p0, p1, e);
        controls.target.lerpVectors(t0, t1, e);
        controls.update();
        if (k < 1) raf = requestAnimationFrame(step);
      };
      raf = requestAnimationFrame(step);
    },
  };
  goto(presets[0]);
  resize();
  applyFrame(0);

  return () => {
    cancelAnimationFrame(raf);
    ro.disconnect();
    controls.dispose();
    scene.traverse((n: any) => {
      n.geometry?.dispose?.();
      (Array.isArray(n.material) ? n.material : n.material ? [n.material] : []).forEach((m: any) => m.dispose?.());
    });
    renderer.dispose();
    renderer.forceContextLoss?.();
    host.replaceChildren();
    api.current = null;
  };
}
