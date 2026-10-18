import { fmtScore, type Bench, type Claim, type Pt } from "@/lib/ai-benchmarks";
import { labColor } from "@/lib/ai-labs";

// The AI desk's pictures, server-rendered SVG, no client code and no chart library. Three rules: lines are labelled where they END (no key to decode), a lab
// wears the same colour on every chart (lib/ai-labs.ts), and a hollow diamond is always a LAB CLAIM that no leaderboard has measured (never part of a line).
//   FrontierChart  — best measured score so far over time; each record dot is coloured by the lab that set it.
//   OpenClosedChart — the closed-weights frontier against the open-weights frontier on one benchmark.
//   LabRaceChart   — each lab's own best-so-far on one benchmark.

type Line = { key: string; color: string; pts: Pt[]; label: string; dashed?: boolean; dots?: boolean };

const DAY = 86_400_000;
const day = (d: string): number => Date.parse(`${d}T00:00:00Z`) / DAY;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const tick = (d: number): string => {
  const dt = new Date(d * DAY);
  return `${MONTHS[dt.getUTCMonth()]} ${dt.getUTCFullYear()}`;
};
const clip = (s: string, n: number): string => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

type Frame = { w: number; h: number; l: number; r: number; t: number; b: number; x0: number; x1: number; lo: number; hi: number };

function frame(bench: Bench, lines: Line[], claims: Claim[], w: number, h: number, right: number): Frame | null {
  const pts = [...lines.flatMap((l) => l.pts), ...claims];
  if (pts.length === 0) return null;
  const xs = pts.map((p) => day(p.d));
  const ys = pts.map((p) => p.s);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs, day(bench.as_of || pts[pts.length - 1].d));
  const bounded = bench.unit === "fraction" && bench.ceiling !== null;
  let lo = Math.min(...ys);
  let hi = Math.max(...ys);
  if (bounded) {
    hi = bench.ceiling ?? 1;
    lo = Math.max(0, Math.floor((lo - (hi - lo) * 0.1) * 10) / 10);
  } else {
    const pad = (hi - lo || Math.abs(hi) || 1) * 0.08;
    lo -= pad;
    hi += pad;
  }
  return { w, h, l: 34, r: right, t: 8, b: 16, x0, x1: x1 === x0 ? x0 + 1 : x1, lo, hi: hi === lo ? lo + 1 : hi };
}

const px = (f: Frame, d: number): number => f.l + ((d - f.x0) / (f.x1 - f.x0)) * (f.w - f.l - f.r);
const py = (f: Frame, v: number): number => f.t + (1 - (v - f.lo) / (f.hi - f.lo)) * (f.h - f.t - f.b);

/** Step path through record points (flat until the next record), extended to the right edge. */
function stepPath(f: Frame, pts: Pt[]): string {
  if (pts.length === 0) return "";
  let d = `M${px(f, day(pts[0].d)).toFixed(1)} ${py(f, pts[0].s).toFixed(1)}`;
  for (let i = 1; i < pts.length; i++) d += ` H${px(f, day(pts[i].d)).toFixed(1)} V${py(f, pts[i].s).toFixed(1)}`;
  return `${d} H${px(f, f.x1).toFixed(1)}`;
}

/** End labels pushed apart so none overlap, in vertical order. */
function spread(rows: { y: number }[], gap = 10): number[] {
  const order = rows.map((r, i) => [r.y, i] as const).sort((a, b) => a[0] - b[0]);
  const out: number[] = new Array(rows.length).fill(0);
  let prev = -Infinity;
  for (const [y, i] of order) {
    prev = Math.max(y, prev + gap);
    out[i] = prev;
  }
  return out;
}

function Chart({ bench, lines, claims = [], title, w = 320, h = 150, right = 96 }: { bench: Bench; lines: Line[]; claims?: Claim[]; title: string; w?: number; h?: number; right?: number }) {
  const f = frame(bench, lines, claims, w, h, right);
  if (!f) return <p className="ai-empty">No scores to draw yet.</p>;
  const ceilingY = bench.unit === "fraction" && bench.ceiling !== null && bench.ceiling < 1.0001 ? py(f, bench.ceiling) : null;
  const labelYs = spread(lines.map((l) => ({ y: py(f, l.pts[l.pts.length - 1]?.s ?? f.lo) })));
  return (
    <svg className="ai-svg" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={title}>
      <title>{title}</title>
      <line x1={f.l} x2={w - f.r} y1={py(f, f.hi)} y2={py(f, f.hi)} className={ceilingY !== null ? "ai-ceiling" : "ai-grid"} />
      <line x1={f.l} x2={w - f.r} y1={py(f, f.lo)} y2={py(f, f.lo)} className="ai-grid" />
      <text x={f.l - 4} y={py(f, f.hi) + 3} textAnchor="end" className="ai-tick">{fmtScore(bench.unit, f.hi)}</text>
      <text x={f.l - 4} y={py(f, f.lo) + 3} textAnchor="end" className="ai-tick">{fmtScore(bench.unit, f.lo)}</text>
      <text x={f.l} y={h - 3} className="ai-tick">{tick(f.x0)}</text>
      <text x={w - f.r} y={h - 3} textAnchor="end" className="ai-tick">{tick(f.x1)}</text>
      {lines.map((l) => (
        <g key={l.key}>
          <path d={stepPath(f, l.pts)} fill="none" stroke={l.color} strokeWidth={1.75} strokeDasharray={l.dashed ? "4 3" : undefined} />
          {l.dots !== false && l.pts.map((p) => (
            <circle key={`${p.d}-${p.m}`} cx={px(f, day(p.d))} cy={py(f, p.s)} r={2.2} fill={labColor(p.l)}>
              <title>{`${p.m}: ${fmtScore(bench.unit, p.s)} (${p.d})`}</title>
            </circle>
          ))}
        </g>
      ))}
      {claims.map((c, i) => {
        const x = px(f, day(c.d));
        const y = py(f, c.s);
        return (
          <path key={`${c.d}-${c.m}-${i}`} d={`M${x} ${y - 4}L${x + 4} ${y}L${x} ${y + 4}L${x - 4} ${y}Z`} className="ai-claim" stroke={labColor(c.l)}>
            <title>{`Claimed by the lab, not independently measured: ${c.m} ${fmtScore(bench.unit, c.s)} (${c.d})`}</title>
          </path>
        );
      })}
      {lines.map((l, i) => (
        <text key={`t-${l.key}`} x={w - f.r + 5} y={labelYs[i] + 3} className="ai-end" fill={l.color}>{clip(l.label, 16)}</text>
      ))}
    </svg>
  );
}

/** Best measured score so far; the last point is labelled with its score and model. */
export function FrontierChart({ bench, claims = true }: { bench: Bench; claims?: boolean }) {
  const last = bench.frontier[bench.frontier.length - 1];
  if (!last) return null;
  const lines: Line[] = [{ key: "frontier", color: "var(--strong)", pts: bench.frontier, label: `${fmtScore(bench.unit, last.s)} ${last.m}` }];
  return <Chart bench={bench} lines={lines} claims={claims ? bench.claimed : []} title={`${bench.name}: best measured score over time. Now ${fmtScore(bench.unit, last.s)} by ${last.m}.`} />;
}

/** Closed-weights frontier against open-weights frontier. */
export function OpenClosedChart({ bench }: { bench: Bench }) {
  if (bench.open.length === 0 || bench.closed.length === 0) return null;
  const o = bench.open[bench.open.length - 1];
  const c = bench.closed[bench.closed.length - 1];
  const lines: Line[] = [
    { key: "closed", color: "var(--strong)", pts: bench.closed, label: `closed ${fmtScore(bench.unit, c.s)}`, dots: false },
    { key: "open", color: "var(--accent)", pts: bench.open, label: `open ${fmtScore(bench.unit, o.s)}`, dots: false },
  ];
  return <Chart bench={bench} lines={lines} title={`${bench.name}: closed-weights frontier ${fmtScore(bench.unit, c.s)}, open-weights frontier ${fmtScore(bench.unit, o.s)}.`} />;
}

/** Each lab's own best-so-far, labelled by lab name in the lab's colour. */
export function LabRaceChart({ bench, names, w = 520, h = 220 }: { bench: Bench; names: Record<string, string>; w?: number; h?: number }) {
  const lines: Line[] = Object.entries(bench.labs)
    .filter(([, pts]) => pts.length > 0)
    .map(([lab, pts]) => ({ key: lab, color: labColor(lab), pts, label: `${names[lab] ?? lab} ${fmtScore(bench.unit, pts[pts.length - 1].s)}`, dots: false }));
  if (lines.length === 0) return null;
  return <Chart bench={bench} lines={lines} title={`${bench.name}: each lab's best score over time.`} w={w} h={h} right={118} />;
}
