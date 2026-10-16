// Camera model for the globe: named views, matrices (rows: screen x, screen y, depth) and the cycling schedule. Pure TS, client-safe.

import { RAD } from "./sphere";

/** Where the camera sits: `elev` is the latitude under the viewer (90 = straight down on the north pole, -90 = from below the
 *  south pole), `roll` turns the picture in its own plane (180 = upside down). The globe always spins about its own axis. */
export type Perspective = { elev: number; roll: number };

export const PERSPECTIVES: readonly Perspective[] = [
  { elev: -72, roll: 0 }, //   from beneath the south pole
  { elev: 14, roll: 180 }, //  upside down
  { elev: 24, roll: -62 }, //  steep diagonal
  { elev: -38, roll: 128 }, // tipped over, southern sky
  { elev: 6, roll: 90 }, //    on its side: the axis runs left to right
  { elev: -52, roll: -34 }, // low and leaning
  { elev: 64, roll: 156 }, //  over the north pole, inverted
];

/** One named camera. Fixed views are (elev, roll); the ecliptic view has the camera fixed in the ecliptic frame, Earth's axis tilted
 *  23.44 degrees from the ecliptic normal and sweeping a cone (precession, stylised to one sweep per `precession` ms). */
export type ViewDef = { id: string; label: string; elev?: number; roll?: number; ecliptic?: boolean };

const quad = (hemi: "N" | "S"): ViewDef[] =>
  [0, 90, 180, 270].map((roll) => ({ id: `${hemi.toLowerCase()}45-${roll}`, label: `${hemi} 45° · ${roll}°`, elev: hemi === "N" ? 45 : -45, roll }));

// Spinning about the axis makes camera azimuth irrelevant (it only shifts which longitude faces us), so the four "azimuths" of a
// 45-degree view are four rolls of the picture: the axis leans up, left, down, right.
/** The systematic set, in a pleasing cycling order (each neighbour is a modest turn from the last). */
export const VIEWS: readonly ViewDef[] = [
  { id: "north-up", label: "North up", elev: 0, roll: 0 },
  ...quad("N"),
  { id: "above-north", label: "From above the North Pole", elev: 90, roll: 0 },
  { id: "ecliptic", label: "Ecliptic · tilt and precession", ecliptic: true },
  { id: "south-up", label: "South up", elev: 0, roll: 180 },
  ...quad("S"),
  { id: "below-south", label: "From below the South Pole", elev: -90, roll: 0 },
];

// ---- cameras: 3x3 rows (screen x, screen y, depth) acting on the polar-axis frame ---------------------------------------------

export type Mat = number[];

/** Camera over latitude `elev` at lon 0, picture rolled by `roll` (before the spin is applied). */
export function fixedView(elev: number, roll: number): Mat {
  const ce = Math.cos(elev * RAD), se = Math.sin(elev * RAD), cr = Math.cos(roll * RAD), sr = Math.sin(roll * RAD);
  const X = [0, 1, 0], Y = [-se, 0, ce], D = [ce, 0, se];
  return [...[0, 1, 2].map((k) => cr * X[k] - sr * Y[k]), ...[0, 1, 2].map((k) => sr * X[k] + cr * Y[k]), ...D];
}

const TILT = 23.44 * RAD; // obliquity of the ecliptic
export const ECL_CAM = 24 * RAD; // how far above the ecliptic plane the camera sits, so its ring reads as an ellipse
const ECL_COS = Math.cos(ECL_CAM);
export const ECL_SIN = Math.sin(ECL_CAM);

/** Ecliptic frame fixed on screen (x right, ecliptic normal leaning up), axis tilted TILT from the normal at azimuth `phi`. */
export function eclipticView(phi: number): Mat {
  const ct = Math.cos(TILT), st = Math.sin(TILT), cp = Math.cos(phi), sp = Math.sin(phi);
  const xb = [ct * cp, ct * sp, -st], yb = [-sp, cp, 0], zb = [st * cp, st * sp, ct]; // body axes in ecliptic coordinates
  const ex = [1, 0, 0], ey = [0, ECL_SIN, -ECL_COS], ez = [0, ECL_COS, ECL_SIN]; // ecliptic axes in screen coordinates
  const toScreen = (b: number[]) => [0, 1, 2].map((r) => ex[r] * b[0] + ey[r] * b[1] + ez[r] * b[2]);
  const cx = toScreen(xb), cy = toScreen(yb), cz = toScreen(zb); // columns of the view matrix
  return [cx[0], cy[0], cz[0], cx[1], cy[1], cz[1], cx[2], cy[2], cz[2]];
}

/** Spin about the polar axis by `theta` first, then the camera `v`. */
export function spun(v: Mat, theta: number): Mat {
  const c = Math.cos(theta), s = Math.sin(theta);
  const out: number[] = [];
  for (let r = 0; r < 3; r++) out.push(v[r * 3] * c + v[r * 3 + 1] * s, -v[r * 3] * s + v[r * 3 + 1] * c, v[r * 3 + 2]);
  return out;
}

const ECL_HOLD = 2.2; // the ecliptic view stays this many times longer, to show a good part of the precession
const ECL_MAX = 60000; // ...but never more than this many ms

const viewMat = (d: ViewDef, clock: number, precession: number): Mat =>
  d.ecliptic ? eclipticView((clock / precession) * 2 * Math.PI) : fixedView(d.elev ?? 0, d.roll ?? 0);

/** Where the camera is at `clock` ms: a view matrix, how "ecliptic" it is (0 or 1, drives the ring and axis), which view's name
 *  to show, and `since` = ms since the last hard cut (Infinity when not cycling). Stateless: the whole schedule is a function of
 *  the clock, so a paused tab resumes seamlessly. Views switch instantly, with no glide. */
/** A deterministic shuffle of 0..n-1 for one pass of the cycle (mulberry32 seeded by seed + pass). */
function passOrder(n: number, seed: number, pass: number): number[] {
  let t = (seed ^ Math.imul(pass + 1, 0x9e3779b1)) >>> 0;
  const rnd = () => {
    t = (t + 0x6d2b79f5) >>> 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
  const o = Array.from({ length: n }, (_, i) => i);
  for (let i = n - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [o[i], o[j]] = [o[j], o[i]];
  }
  return o;
}

/** Random order, every view once per pass, never the same view twice in a row across a pass boundary. */
function orderFor(n: number, seed: number, pass: number): number[] {
  const o = passOrder(n, seed, pass);
  if (pass > 0 && n > 1) {
    const prev = passOrder(n, seed, pass - 1);
    if (o[0] === prev[n - 1]) [o[0], o[1]] = [o[1], o[0]];
  }
  return o;
}

export function cameraAt(views: readonly ViewDef[], clock: number, hold: number, precession: number, seed = 0): { v: Mat; ecl: number; label: number; since: number } {
  if (views.length === 1) return { v: viewMat(views[0], clock, precession), ecl: views[0].ecliptic ? 1 : 0, label: 0, since: Infinity };
  const dur = views.map((d) => (d.ecliptic ? Math.max(hold, Math.min(hold * ECL_HOLD, ECL_MAX)) : hold));
  const total = dur.reduce((a, b) => a + b, 0);
  const pass = Math.floor(clock / total);
  const order = orderFor(views.length, seed, pass);
  let p = clock - pass * total, k = 0;
  while (p >= dur[order[k]]) p -= dur[order[k++]];
  const i = order[k];
  return { v: viewMat(views[i], clock, precession), ecl: views[i].ecliptic ? 1 : 0, label: i, since: p };
}
