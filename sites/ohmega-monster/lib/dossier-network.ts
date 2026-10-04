import type { Actor, Relation } from "./dossier";

// Deterministic layout of the actor network, computed at build time (no packages, no randomness):
// pick the most-mentioned actors, seed them on an ellipse with strongly linked actors adjacent, then
// relax with a small force simulation (repulsion, edge springs, gravity). Same input, same picture.

export const NET_W = 700;
export const NET_H = 420;
const PAD_X = 120; // room for the labels on the left and right
const PAD_Y = 30;

export const RELATION_KIND_KEYS = ["strikes", "sabotage", "coerces", "sanctions", "supports", "negotiates", "deters", "other"] as const;
export type RelationKind = (typeof RELATION_KIND_KEYS)[number];
export const kindOf = (k: string): RelationKind => ((RELATION_KIND_KEYS as readonly string[]).includes(k) ? (k as RelationKind) : "other");

export type NetNode = { name: string; mentions: number; x: number; y: number; r: number; label: string; lx: number; ly: number; anchor: "start" | "end" | "middle" };
export type NetEdge = { rel: Relation; kind: RelationKind; d: string; width: number };
export type Network = { nodes: NetNode[]; edges: NetEdge[]; hiddenActors: number };

const f1 = (n: number) => Math.round(n * 10) / 10;

export function layoutNetwork(actors: Actor[], relations: Relation[], limit = 12): Network {
  // Weight of every name: its own mentions plus the relations it takes part in.
  const weight = new Map<string, { mentions: number; rel: number }>();
  const touch = (name: string) => {
    let w = weight.get(name);
    if (!w) weight.set(name, (w = { mentions: 0, rel: 0 }));
    return w;
  };
  for (const a of actors) touch(a.name).mentions += a.mentions;
  const linked = relations.filter((r) => r.source !== r.target);
  for (const r of linked) {
    touch(r.source).rel += r.count;
    touch(r.target).rel += r.count;
  }
  // Only actors that have a relation can sit in a network; the others are listed elsewhere.
  const ranked = [...weight.entries()]
    .filter(([, w]) => w.rel > 0)
    .sort((a, b) => b[1].mentions + b[1].rel - (a[1].mentions + a[1].rel) || a[0].localeCompare(b[0]));
  const kept = ranked.slice(0, limit).map(([name]) => name);
  const keptSet = new Set(kept);
  const edgesIn = linked.filter((r) => keptSet.has(r.source) && keptSet.has(r.target));
  const n = kept.length;
  if (n < 2) return { nodes: [], edges: [], hiddenActors: Math.max(0, ranked.length - n) };

  // Pairwise link strength, for the seed order and the springs.
  const pair = (a: string, b: string) => (a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`);
  const strength = new Map<string, number>();
  for (const r of edgesIn) strength.set(pair(r.source, r.target), (strength.get(pair(r.source, r.target)) ?? 0) + r.count);

  // Seed order: heaviest first, then always the unplaced actor most strongly tied to the one just placed.
  const order: string[] = [kept[0]];
  const left = new Set(kept.slice(1));
  while (left.size > 0) {
    const prev = order[order.length - 1];
    let best = "";
    let bestS = -1;
    for (const name of kept) {
      if (!left.has(name)) continue;
      const s = strength.get(pair(prev, name)) ?? 0;
      if (s > bestS) {
        bestS = s;
        best = name;
      }
    }
    order.push(best);
    left.delete(best);
  }

  const cx = NET_W / 2;
  const cy = NET_H / 2;
  const rx = NET_W / 2 - PAD_X;
  const ry = NET_H / 2 - PAD_Y;
  const pos = order.map((_, i) => {
    const a = (i / n) * Math.PI * 2 - Math.PI / 2;
    return { x: cx + Math.cos(a) * rx, y: cy + Math.sin(a) * ry };
  });
  const index = new Map(order.map((name, i) => [name, i]));
  const springs = edgesIn.map((r) => ({ a: index.get(r.source) as number, b: index.get(r.target) as number, w: 1 + Math.log(1 + (strength.get(pair(r.source, r.target)) ?? 1)) }));

  const k = Math.sqrt(((NET_W - PAD_X * 2) * (NET_H - PAD_Y * 2)) / n) * 0.9;
  const iters = 260;
  for (let it = 0; it < iters; it++) {
    const temp = (1 - it / iters) * 14 + 0.4;
    const dx = new Array<number>(n).fill(0);
    const dy = new Array<number>(n).fill(0);
    for (let i = 0; i < n; i++)
      for (let j = i + 1; j < n; j++) {
        const ex = pos[i].x - pos[j].x;
        const ey = pos[i].y - pos[j].y;
        const d = Math.max(1, Math.hypot(ex, ey));
        const rep = (k * k) / d;
        dx[i] += (ex / d) * rep;
        dy[i] += (ey / d) * rep;
        dx[j] -= (ex / d) * rep;
        dy[j] -= (ey / d) * rep;
      }
    for (const s of springs) {
      const ex = pos[s.a].x - pos[s.b].x;
      const ey = pos[s.a].y - pos[s.b].y;
      const d = Math.max(1, Math.hypot(ex, ey));
      const att = ((d * d) / k) * 0.14 * s.w;
      dx[s.a] -= (ex / d) * att;
      dy[s.a] -= (ey / d) * att;
      dx[s.b] += (ex / d) * att;
      dy[s.b] += (ey / d) * att;
    }
    for (let i = 0; i < n; i++) {
      dx[i] -= (pos[i].x - cx) * 0.9;
      dy[i] -= (pos[i].y - cy) * 0.9 * (NET_W / NET_H) * 0.6;
      const len = Math.hypot(dx[i], dy[i]) || 1;
      const step = Math.min(len, temp);
      pos[i].x = Math.min(NET_W - PAD_X, Math.max(PAD_X, pos[i].x + (dx[i] / len) * step));
      pos[i].y = Math.min(NET_H - PAD_Y, Math.max(PAD_Y, pos[i].y + (dy[i] / len) * step));
    }
  }

  const maxMentions = Math.max(1, ...order.map((name) => weight.get(name)?.mentions ?? 0));
  const nodes: NetNode[] = order.map((name, i) => {
    const mentions = weight.get(name)?.mentions ?? 0;
    const r = 6 + 12 * Math.sqrt(mentions / maxMentions); // area ~ mentions
    return { name, mentions, x: f1(pos[i].x), y: f1(pos[i].y), r: f1(r), label: name, lx: 0, ly: 0, anchor: "middle" };
  });

  // Edges: parallel and opposite relations between the same two actors fan out around the straight line.
  const maxCount = Math.max(1, ...edgesIn.map((r) => r.count));
  const groups = new Map<string, Relation[]>();
  for (const r of edgesIn) {
    const key = pair(r.source, r.target);
    groups.set(key, [...(groups.get(key) ?? []), r]);
  }
  const edges: NetEdge[] = [];
  for (const [key, group] of groups) {
    const [na, nb] = key.split("\u0000");
    const A = nodes[index.get(na) as number];
    const B = nodes[index.get(nb) as number];
    const len = Math.hypot(B.x - A.x, B.y - A.y) || 1;
    const nx = -(B.y - A.y) / len; // one canonical normal per pair, so every edge fans consistently
    const ny = (B.x - A.x) / len;
    group.forEach((rel, gi) => {
      const off = (gi - (group.length - 1) / 2) * 34;
      const s = nodes[index.get(rel.source) as number];
      const t = nodes[index.get(rel.target) as number];
      const mx = (s.x + t.x) / 2 + nx * off;
      const my = (s.y + t.y) / 2 + ny * off;
      const u1 = unit(mx - s.x, my - s.y);
      const u2 = unit(t.x - mx, t.y - my);
      const sx = s.x + u1[0] * (s.r + 2);
      const sy = s.y + u1[1] * (s.r + 2);
      const ex = t.x - u2[0] * (t.r + 8);
      const ey = t.y - u2[1] * (t.r + 8);
      edges.push({
        rel,
        kind: kindOf(rel.kind),
        d: `M${f1(sx)},${f1(sy)} Q${f1(mx)},${f1(my)} ${f1(ex)},${f1(ey)}`,
        width: f1(1 + 3.5 * Math.sqrt(rel.count / maxCount)),
      });
    });
  }
  // Heaviest drawn last, so the thick lines are on top.
  edges.sort((a, b) => a.rel.count - b.rel.count);
  placeLabels(nodes, edgesIn, index, cx, cy);
  return { nodes, edges, hiddenActors: Math.max(0, ranked.length - n) };
}

/**
 * Each label goes in the direction (of eight) that keeps clearest of the lines touching its node,
 * preferring the side facing away from the middle, then horizontal. Long names are cut to the room left.
 */
function placeLabels(nodes: NetNode[], rels: Relation[], index: Map<string, number>, cx: number, cy: number): void {
  const angles = nodes.map(() => [] as number[]);
  for (const r of rels) {
    const a = index.get(r.source) as number;
    const b = index.get(r.target) as number;
    angles[a].push(Math.atan2(nodes[b].y - nodes[a].y, nodes[b].x - nodes[a].x));
    angles[b].push(Math.atan2(nodes[a].y - nodes[b].y, nodes[a].x - nodes[b].x));
  }
  const diff = (a: number, b: number) => {
    const d = Math.abs(a - b) % (Math.PI * 2);
    return d > Math.PI ? Math.PI * 2 - d : d;
  };
  nodes.forEach((n, i) => {
    const away = Math.atan2(n.y - cy, n.x - cx);
    let best = { score: -Infinity, cos: 1, sin: 0, anchor: "start" as NetNode["anchor"], lx: 0, ly: 0 };
    for (let k = 0; k < 8; k++) {
      const a = (k * Math.PI) / 4;
      const cos = Math.cos(a);
      const sin = Math.sin(a);
      const anchor: NetNode["anchor"] = cos > 0.3 ? "start" : cos < -0.3 ? "end" : "middle";
      const lx = n.x + cos * (n.r + 6);
      const ly = n.y + sin * (n.r + 7) + (anchor === "middle" ? (sin > 0 ? 11 : -3) : 4);
      if (ly < 12 || ly > NET_H - 4) continue;
      const clear = angles[i].length ? Math.min(...angles[i].map((e) => diff(e, a))) : Math.PI;
      const score = Math.min(clear, 1.6) + 0.5 * Math.cos(diff(a, away)) + (anchor !== "middle" ? 0.15 : 0);
      if (score > best.score) best = { score, cos, sin, anchor, lx, ly };
    }
    const room = best.anchor === "start" ? NET_W - best.lx - 4 : best.anchor === "end" ? best.lx - 4 : 2 * Math.min(best.lx, NET_W - best.lx) - 8;
    const chars = Math.max(6, Math.floor(room / 7.4));
    n.label = n.name.length > chars ? `${n.name.slice(0, chars - 1)}…` : n.name;
    n.anchor = best.anchor;
    n.lx = f1(best.lx);
    n.ly = f1(best.ly);
  });
}

function unit(x: number, y: number): [number, number] {
  const l = Math.hypot(x, y) || 1;
  return [x / l, y / l];
}
