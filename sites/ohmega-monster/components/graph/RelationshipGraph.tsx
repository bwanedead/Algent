"use client";

import Link from "next/link";
import { useEffect, useMemo, useReducer, useRef, useState } from "react";

import type { EntityGraph } from "@/lib/entities";

import "./graph.css";

// The relationship browser: states and theaters as one network, laid out by a tiny force simulation (no library). Circles are
// states, squares are theaters; size is how much each is involved; a theater's colour is where it is heading. Drag to pan,
// pinch or wheel to zoom, tap a node to focus its neighbourhood and read its connections in the panel (which links to the pages).

const W = 800;
const H = 600;
const WARM = 140; // ticks run before the first paint, so the picture arrives settled
const MIN_K = 0.4;
const MAX_K = 4;

type Dir = "rising" | "steady" | "easing" | "unclear";
const DIR_WORD: Record<Dir, string> = { rising: "escalating", steady: "steady", easing: "easing", unclear: "unclear" };

type Node = { id: string; kind: "a" | "t"; label: string; key: string; r: number; x: number; y: number; vx: number; vy: number; dir: Dir; linked: boolean; w: number };
type Edge = { a: number; b: number; w: number };

function build(g: EntityGraph): { nodes: Node[]; edges: Edge[] } {
  const maxA = Math.max(1, ...g.actors.map((a) => a.weight));
  const maxT = Math.max(1, ...g.theaters.map((t) => t.weight));
  const nodes: Node[] = [
    ...g.theaters.map((t, i): Node => ({ id: `t:${t.id}`, kind: "t", label: t.name, key: t.id, r: 7 + 11 * Math.sqrt(t.weight / maxT), x: 0, y: 0, vx: 0, vy: 0, dir: t.direction, linked: t.linked, w: t.weight, ...ring(i, g.theaters.length, 140) })),
    ...g.actors.map((a, i): Node => ({ id: `a:${a.iso2}`, kind: "a", label: a.name, key: a.iso2, r: 4 + 9 * Math.sqrt(a.weight / maxA), x: 0, y: 0, vx: 0, vy: 0, dir: "unclear", linked: true, w: a.weight, ...ring(i, g.actors.length, 250) })),
  ];
  const at = new Map(nodes.map((n, i) => [n.id, i]));
  const edges = g.links.flatMap((l): Edge[] => {
    const a = at.get(`a:${l.iso2}`);
    const b = at.get(`t:${l.theater}`);
    return a !== undefined && b !== undefined ? [{ a, b, w: l.w }] : [];
  });
  return { nodes, edges };
}

/** A deterministic start on a ring, so the same data always settles to the same picture. */
function ring(i: number, n: number, radius: number): { x: number; y: number } {
  const t = (i / Math.max(1, n)) * Math.PI * 2;
  const wobble = 1 + 0.12 * Math.sin(i * 7.3);
  return { x: Math.cos(t) * radius * wobble, y: Math.sin(t) * radius * wobble };
}

/** One step of the simulation: nodes repel, edges are springs, a faint pull keeps everything near the middle. */
function step(nodes: Node[], edges: Edge[], alpha: number) {
  for (let i = 0; i < nodes.length; i++) {
    const p = nodes[i];
    for (let j = i + 1; j < nodes.length; j++) {
      const q = nodes[j];
      const dx = p.x - q.x;
      const dy = p.y - q.y;
      const d2 = Math.max(dx * dx + dy * dy, 120);
      const f = (2600 * alpha) / d2;
      const d = Math.sqrt(d2);
      p.vx += (dx / d) * f;
      p.vy += (dy / d) * f;
      q.vx -= (dx / d) * f;
      q.vy -= (dy / d) * f;
    }
  }
  for (const e of edges) {
    const p = nodes[e.a];
    const q = nodes[e.b];
    const dx = q.x - p.x;
    const dy = q.y - p.y;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    const f = ((d - 90) / d) * 0.05 * alpha * Math.min(2, 0.6 + Math.log2(1 + e.w));
    p.vx += dx * f;
    p.vy += dy * f;
    q.vx -= dx * f;
    q.vy -= dy * f;
  }
  for (const n of nodes) {
    n.vx -= n.x * 0.012 * alpha;
    n.vy -= n.y * 0.012 * alpha;
    n.vx *= 0.8;
    n.vy *= 0.8;
    n.x += n.vx;
    n.y += n.vy;
  }
}

type View = { x: number; y: number; k: number };
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export default function RelationshipGraph({ graph }: { graph: EntityGraph }) {
  const sim = useMemo(() => {
    const s = build(graph);
    let alpha = 1;
    for (let i = 0; i < WARM; i++, alpha *= 0.975) step(s.nodes, s.edges, alpha);
    return { ...s, alpha };
  }, [graph]);
  const [, redraw] = useReducer((n: number) => n + 1, 0);
  const [view, setView] = useState<View>({ x: W / 2, y: H / 2, k: 1 });
  const [sel, setSel] = useState<string | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<{ moved: number; pinch: number }>({ moved: 0, pinch: 0 });

  // Let the picture finish settling (skipped for people who ask for less motion: it simply stays as warmed up).
  useEffect(() => {
    const calm = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (calm) return;
    let alpha = sim.alpha;
    let raf = 0;
    const tick = () => {
      step(sim.nodes, sim.edges, alpha);
      alpha *= 0.975;
      redraw();
      if (alpha > 0.02) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [sim]);

  // Wheel zoom needs a non-passive listener to keep the page from scrolling under it.
  useEffect(() => {
    const el = svg.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      zoomBy(e.deltaY < 0 ? 1.15 : 1 / 1.15);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const zoomBy = (f: number) => setView((v) => ({ ...v, k: clamp(v.k * f, MIN_K, MAX_K) }));
  const unit = () => W / (svg.current?.getBoundingClientRect().width || W); // viewBox units per screen pixel

  const onDown = (e: React.PointerEvent) => {
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    gesture.current = { moved: 0, pinch: 0 };
  };
  const onMove = (e: React.PointerEvent) => {
    const prev = pointers.current.get(e.pointerId);
    if (!prev) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const pts = Array.from(pointers.current.values());
    if (pts.length >= 2) {
      const d = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      if (gesture.current.pinch > 0) zoomBy(d / gesture.current.pinch);
      gesture.current.pinch = d;
      gesture.current.moved = 99;
      return;
    }
    const dx = e.clientX - prev.x;
    const dy = e.clientY - prev.y;
    gesture.current.moved += Math.abs(dx) + Math.abs(dy);
    if (gesture.current.moved > 6) setView((v) => ({ ...v, x: v.x + dx * unit(), y: v.y + dy * unit() }));
  };
  const onUp = (e: React.PointerEvent) => {
    pointers.current.delete(e.pointerId);
    gesture.current.pinch = 0;
  };
  /** A tap (not a drag) picks the node under it, or clears the focus on empty ground. */
  const pick = (id: string | null) => {
    if (gesture.current.moved <= 6) setSel(id);
  };

  const byId = useMemo(() => new Map(sim.nodes.map((n, i) => [n.id, i])), [sim]);
  const adj = useMemo(() => {
    const m = new Map<number, number[]>();
    for (const e of sim.edges) {
      m.set(e.a, [...(m.get(e.a) ?? []), e.b]);
      m.set(e.b, [...(m.get(e.b) ?? []), e.a]);
    }
    return m;
  }, [sim]);
  const focus = sel !== null ? byId.get(sel) ?? null : null;
  const near = useMemo(() => new Set(focus === null ? [] : [focus, ...(adj.get(focus) ?? [])]), [focus, adj]);
  // Shared-theater links between states, only for the focused state (all of them at once would be a hairball).
  const peers = useMemo(() => {
    if (focus === null || sim.nodes[focus].kind !== "a") return [];
    const out = new Map<number, number[]>();
    for (const t of adj.get(focus) ?? []) for (const o of adj.get(t) ?? []) if (o !== focus) out.set(o, [...(out.get(o) ?? []), t]);
    return Array.from(out, ([o, via]) => ({ o, via })).sort((x, y) => y.via.length - x.via.length || sim.nodes[x.o].label.localeCompare(sim.nodes[y.o].label));
  }, [focus, adj, sim]);

  const labelled = (i: number) => focus === null ? sim.nodes[i].kind === "t" || sim.nodes[i].r > 9 || view.k > 1.8 : near.has(i);
  const selNode = focus !== null ? sim.nodes[focus] : null;
  const nodeHref = (n: Node) => (n.kind === "a" ? `/intel/actors/${n.key}` : n.linked ? `/intel/theaters/${n.key}` : null);

  return (
    <div className="rg">
      <div className="rg-stage">
        <svg
          ref={svg}
          viewBox={`0 0 ${W} ${H}`}
          className="rg-svg"
          role="group"
          aria-label={`Relationship browser: ${graph.actors.length} states and ${graph.theaters.length} theaters. Choose a node to read its connections in the panel.`}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerCancel={onUp}
          onClick={() => pick(null)}
        >
          <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
            {sim.edges.map((e, i) => {
              const p = sim.nodes[e.a];
              const q = sim.nodes[e.b];
              const on = focus !== null && (e.a === focus || e.b === focus);
              return <line key={i} x1={p.x} y1={p.y} x2={q.x} y2={q.y} className={`rg-edge${on ? " is-on" : focus !== null ? " is-dim" : ""}`} strokeWidth={0.6 + Math.min(2.4, Math.log2(1 + e.w) * 0.5)} />;
            })}
            {peers.slice(0, 12).map(({ o }) => (
              <line key={`p${o}`} x1={sim.nodes[focus as number].x} y1={sim.nodes[focus as number].y} x2={sim.nodes[o].x} y2={sim.nodes[o].y} className="rg-peer" />
            ))}
            {sim.nodes.map((n, i) => {
              const dim = focus !== null && !near.has(i);
              const cls = `rg-node ${n.kind === "t" ? `is-t is-${n.dir}` : "is-a"}${i === focus ? " is-sel" : ""}${dim ? " is-dim" : ""}`;
              return (
                <g
                  key={n.id}
                  transform={`translate(${n.x} ${n.y})`}
                  className={cls}
                  role="button"
                  tabIndex={0}
                  aria-pressed={i === focus}
                  aria-label={`${n.label}${n.kind === "t" ? `, theater, ${DIR_WORD[n.dir]}` : ", state"}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    pick(n.id);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSel(n.id);
                    }
                  }}
                >
                  <title>{n.label}</title>
                  {n.kind === "t" ? <rect x={-n.r} y={-n.r} width={n.r * 2} height={n.r * 2} rx={2} /> : <circle r={n.r} />}
                  {labelled(i) && (
                    <text y={-n.r - 3} textAnchor="middle" className="rg-label">
                      {n.label}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
        <div className="rg-tools" role="group" aria-label="Zoom">
          <button type="button" onClick={() => zoomBy(1.3)} aria-label="Zoom in">+</button>
          <button type="button" onClick={() => zoomBy(1 / 1.3)} aria-label="Zoom out">−</button>
          <button type="button" onClick={() => setView({ x: W / 2, y: H / 2, k: 1 })} aria-label="Reset the view">⌂</button>
        </div>
        <ul className="rg-key" aria-label="Key">
          <li><i className="rg-sw is-a" /> state</li>
          <li><i className="rg-sw is-t is-rising" /> theater escalating</li>
          <li><i className="rg-sw is-t is-steady" /> steady</li>
          <li><i className="rg-sw is-t is-easing" /> easing</li>
          <li><i className="rg-sw is-t is-unclear" /> unclear</li>
        </ul>
      </div>

      <aside className="rg-panel" aria-live="polite">
        {selNode === null ? (
          <>
            <h2>Everything linked to everything</h2>
            <p>Tap a state or a theater to see what it is connected to. Bigger means more involved; a theater&apos;s colour is where it is heading. Drag to move, pinch or use the buttons to zoom.</p>
          </>
        ) : (
          <>
            <h2>{selNode.label}</h2>
            <p className="rg-sub">
              {selNode.kind === "t" ? `Theater · ${DIR_WORD[selNode.dir]}` : "State"} · {(adj.get(focus as number) ?? []).length} connection{(adj.get(focus as number) ?? []).length === 1 ? "" : "s"}
            </p>
            {nodeHref(selNode) && (
              <p>
                <Link href={nodeHref(selNode) as string} className="xt">
                  Open its page →
                </Link>
              </p>
            )}
            <h3>{selNode.kind === "t" ? "States involved" : "Theaters it is in"}</h3>
            <ul>
              {(adj.get(focus as number) ?? [])
                .map((j) => sim.nodes[j])
                .sort((a, b) => b.w - a.w || a.label.localeCompare(b.label))
                .map((n) => (
                  <li key={n.id}>
                    <button type="button" className="rg-pick" onClick={() => setSel(n.id)} aria-label={`Focus ${n.label}`}>
                      {n.label}
                    </button>
                    {nodeHref(n) && (
                      <Link href={nodeHref(n) as string} className="rg-go" aria-label={`Open ${n.label}`}>
                        ↗
                      </Link>
                    )}
                  </li>
                ))}
            </ul>
            {peers.length > 0 && (
              <>
                <h3>Shares a theater with</h3>
                <ul>
                  {peers.slice(0, 12).map(({ o, via }) => (
                    <li key={o}>
                      <button type="button" className="rg-pick" onClick={() => setSel(sim.nodes[o].id)} aria-label={`Focus ${sim.nodes[o].label}`}>
                        {sim.nodes[o].label}
                      </button>
                      <span className="rg-via"> · {via.map((t) => sim.nodes[t].label).join(", ")}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <p>
              <button type="button" className="rg-pick" onClick={() => setSel(null)}>
                Clear focus
              </button>
            </p>
          </>
        )}
      </aside>
    </div>
  );
}
