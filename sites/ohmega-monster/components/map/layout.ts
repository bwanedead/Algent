import type { MapCountryLabel, TheaterMap } from "@/lib/daily";

// Label placement for GeoMap, as a pure function of the spec and the rendered scale `k` (CSS px per
// viewBox unit). The backend sends candidates in priority order; what actually fits depends on the screen,
// so placement is greedy and collision-checked here: event marks first, then the instrument callout,
// then place names, the names of disputed areas, capitals, country names, and finally the other cities. Whatever does not fit is
// dropped — a label is never drawn over another, and the map never needs a legend to be read.

type Box = { x0: number; y0: number; x1: number; y1: number };
type Anchor = "start" | "middle" | "end";
export type Placed = { x: number; y: number; anchor: Anchor; text: string };

export type MapLayout = {
  markR: number; // px
  markPx: number;
  cityPx: number;
  notePx: number;
  markPos: { x: number; y: number }[];
  placeLabels: (Placed | null)[];
  disputedLabels: { text: string; x: number; y: number; anchor: Anchor; px: number }[];
  countryLabels: { text: string; x: number; y: number; px: number }[];
  cities: { name: string; x: number; y: number; capital: boolean; label: Placed | null }[];
  annotations: { x: number; y: number; box: { x: number; y: number; w: number; h: number }; rows: string[]; leader: { x: number; y: number } }[];
  locator: { w: number; h: number } | null;
};

const CAPS = 0.74; // average glyph width / font size, uppercase with tracking
const LOWER = 0.56;
const MAX_PLACE_LABELS = 8; // beyond this the numbers carry the map and the list names the places

/** "Taiz, Yemen" -> "Taiz": the country is already written on the map. */
export function shortPlace(label: string): string {
  const head = label.split(/[,(—–-]/)[0].trim();
  return head.length > 22 ? head.slice(0, 21) + "…" : head;
}

/** v1 maps carry no label anchors: seat each name at the centre of its largest piece (as before). */
function legacyLabels(map: TheaterMap): MapCountryLabel[] {
  const out: MapCountryLabel[] = [];
  for (const c of map.countries) {
    if (!c.name) continue;
    let best: { w: number; h: number; x: number; y: number } | null = null;
    for (const sub of c.d.split(/(?=M)/)) {
      const nums = (sub.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number);
      if (nums.length < 6) continue;
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (let i = 0; i + 1 < nums.length; i += 2) {
        x0 = Math.min(x0, nums[i]); x1 = Math.max(x1, nums[i]);
        y0 = Math.min(y0, nums[i + 1]); y1 = Math.max(y1, nums[i + 1]);
      }
      const w = x1 - x0, h = y1 - y0;
      if (!best || w * h > best.w * best.h) best = { w, h, x: (x0 + x1) / 2, y: (y0 + y1) / 2 };
    }
    if (best && best.w > 40 && best.h > 40) out.push({ name: c.name, x: best.x, y: best.y, r: Math.min(best.w, best.h) / 2, key: false });
  }
  return out;
}

export function layoutMap(map: TheaterMap, k: number): MapLayout {
  const W = map.width, H = map.height;
  const u = (px: number) => px / k;
  const phone = k * W < 520;
  const markPx = phone ? 9 : 10;
  const cityPx = phone ? 10.5 : 11.5;
  const notePx = phone ? 10.5 : 11.5;
  const taken: Box[] = [];
  const inside = (b: Box) => b.x0 >= 0 && b.y0 >= 0 && b.x1 <= W && b.y1 <= H;
  const free = (b: Box) => inside(b) && !taken.some((t) => b.x0 < t.x1 && b.x1 > t.x0 && b.y0 < t.y1 && b.y1 > t.y0);
  const textW = (s: string, px: number, caps = false) => u(s.length * px * (caps ? CAPS : LOWER));
  const side = (x: number, y: number, text: string, px: number, gap: number): Placed | null => {
    const w = textW(text, px), h = u(px * 1.3);
    const tries: [Anchor, number, number, Box][] = [
      ["start", x + gap, y, { x0: x + gap, x1: x + gap + w, y0: y - h / 2, y1: y + h / 2 }],
      ["end", x - gap, y, { x0: x - gap - w, x1: x - gap, y0: y - h / 2, y1: y + h / 2 }],
      ["middle", x, y - gap - h * 0.15, { x0: x - w / 2, x1: x + w / 2, y0: y - gap - h * 1.15, y1: y - gap - h * 0.15 }],
      ["middle", x, y + gap + h * 0.65, { x0: x - w / 2, x1: x + w / 2, y0: y + gap - h * 0.1, y1: y + gap + h * 1.1 }],
    ];
    for (const [anchor, tx, ty, b] of tries) {
      if (free(b)) {
        taken.push(b);
        return { x: tx, y: ty, anchor, text };
      }
    }
    return null;
  };

  // Event marks. Marks at the same spot sit side by side (a row centred on the true location) so none hides another.
  const r = u(markPx === 9 ? 9 : 10);
  const groups = new Map<string, number[]>();
  map.points.forEach((p, i) => {
    const key = `${Math.round(p.x / (2 * r))}:${Math.round(p.y / (2 * r))}`;
    groups.set(key, [...(groups.get(key) ?? []), i]);
  });
  const markPos = map.points.map((p) => ({ x: p.x, y: p.y }));
  for (const idxs of groups.values()) {
    if (idxs.length < 2) continue;
    const cx = idxs.reduce((s, i) => s + map.points[i].x, 0) / idxs.length;
    idxs.forEach((i, j) => { markPos[i] = { x: cx + (j - (idxs.length - 1) / 2) * 2.2 * r, y: map.points[i].y }; });
  }
  markPos.forEach((p) => taken.push({ x0: p.x - r - u(2), x1: p.x + r + u(2), y0: p.y - r - u(2), y1: p.y + r + u(2) }));

  // Corner furniture (scale bar bottom-left, locator top-right) is not available to labels.
  if (map.scale) taken.push({ x0: 0, y0: H - u(40), x1: u(12) + map.scale.px + u(8), y1: H });
  let locator: { w: number; h: number } | null = null;
  if (map.locator) {
    const w = u(Math.max(80, Math.min(140, k * W * 0.2)));
    locator = { w, h: (w * map.locator.height) / map.locator.width };
    taken.push({ x0: W - w - u(10), y0: 0, x1: W, y1: locator.h + u(10) });
  }

  // Instrument callouts: the number beside the chokepoint, with a short leader.
  const annotations: MapLayout["annotations"] = [];
  for (const a of map.annotations) {
    const rows = [a.title, ...a.lines];
    const w = Math.max(...rows.map((s) => textW(s, notePx))) + u(12);
    const h = u(notePx * 1.25) * rows.length + u(12);
    const d = u(14);
    const spots: [number, number][] = [[a.x + d, a.y - h - d / 2], [a.x - w - d, a.y - h - d / 2], [a.x + d, a.y + d / 2], [a.x - w - d, a.y + d / 2],
      [a.x + d, a.y - h / 2], [a.x - w - d, a.y - h / 2], [a.x - w / 2, a.y - h - d], [a.x - w / 2, a.y + d]];
    const spot = spots.find(([x, y]) => free({ x0: x, y0: y, x1: x + w, y1: y + h })) ?? spots.find(([x, y]) => inside({ x0: x, y0: y, x1: x + w, y1: y + h }));
    if (!spot) continue;
    const [bx, by] = spot;
    taken.push({ x0: bx - u(2), y0: by - u(2), x1: bx + w + u(2), y1: by + h + u(2) });
    annotations.push({ x: a.x, y: a.y, box: { x: bx, y: by, w, h }, rows,
      leader: { x: Math.max(bx, Math.min(a.x, bx + w)), y: Math.max(by, Math.min(a.y, by + h)) } });
  }

  const placeLabels: (Placed | null)[] = map.points.map(() => null);
  if (map.points.length <= MAX_PLACE_LABELS) {
    const said = new Set<string>();
    map.points.forEach((p, i) => {
      const text = shortPlace(p.label);
      if (!text || said.has(text)) return;
      said.add(text);
      placeLabels[i] = side(markPos[i].x, markPos[i].y, text, cityPx, r + u(3));
    });
  }

  // Disputed/occupied areas: named at the area (centred if it fits, else beside it); one name per area name.
  const disputedLabels: MapLayout["disputedLabels"] = [];
  const named = new Set<string>();
  const dpx = cityPx - 1;
  for (const a of map.disputed) {
    if (named.has(a.name)) continue;
    const text = a.name.length > 24 ? a.name.slice(0, 23) + "…" : a.name;
    const w = textW(text, dpx), h = u(dpx * 1.3);
    const b = { x0: a.x - w / 2, x1: a.x + w / 2, y0: a.y - h / 2, y1: a.y + h / 2 };
    if (free(b)) {
      taken.push(b);
      disputedLabels.push({ text, x: a.x, y: a.y, anchor: "middle", px: dpx });
      named.add(a.name);
      continue;
    }
    const beside = side(a.x, a.y, text, dpx, u(4));
    if (beside) {
      disputedLabels.push({ text, x: beside.x, y: beside.y, anchor: beside.anchor, px: dpx });
      named.add(a.name);
    }
  }

  const placeCity = (c: { name: string; x: number; y: number; capital: boolean }) => {
    const dot = { x0: c.x - u(4), x1: c.x + u(4), y0: c.y - u(4), y1: c.y + u(4) };
    if (!free(dot)) return null; // sits under a mark or another label: the mark already says where
    taken.push(dot);
    return { ...c, label: side(c.x, c.y, c.name, cityPx, u(6)) };
  };
  const cities: MapLayout["cities"] = [];
  for (const c of map.cities.filter((c) => c.capital)) {
    const placed = placeCity(c);
    if (placed?.label) cities.push(placed);
  }

  const countryLabels: MapLayout["countryLabels"] = [];
  const labels = map.labels.length > 0 ? map.labels : legacyLabels(map);
  for (const l of [...labels].sort((a, b) => Number(b.key) - Number(a.key) || b.r - a.r)) {
    const text = l.name.toUpperCase();
    const roomPx = 2.4 * l.r * k; // the text may overhang the border a little, as it does on any atlas
    const px = Math.min(cityPx - 1, roomPx / (text.length * CAPS));
    if (px < 8.5 && !l.key) continue;
    const fit = Math.max(px, 8.5);
    const w = textW(text, fit, true), h = u(fit * 1.3);
    for (const dy of [0, -u(16), u(16), -u(32), u(32)]) {
      const b = { x0: l.x - w / 2, x1: l.x + w / 2, y0: l.y + dy - h / 2, y1: l.y + dy + h / 2 };
      if (free(b)) {
        taken.push(b);
        countryLabels.push({ text, x: l.x, y: l.y + dy, px: fit });
        break;
      }
    }
  }

  for (const c of map.cities.filter((c) => !c.capital)) {
    const placed = placeCity(c);
    if (placed?.label) cities.push(placed);
  }

  return { markR: markPx === 9 ? 9 : 10, markPx, cityPx, notePx, markPos, placeLabels, disputedLabels, countryLabels, cities, annotations, locator };
}
