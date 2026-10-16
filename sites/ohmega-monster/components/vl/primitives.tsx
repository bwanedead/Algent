import type { Direction } from "@/lib/intel";

import Glyph from "./Glyph";

// Shared small encodings that replace sentences: a coloured direction mark, a heat bar, a sparkline, a big numeral with a tiny label,
// a freshness dot. Styles live in app/visual.css (`vl-*`); colour tokens are the --vl-* set, both themes. Server- and client-safe.

const DIR_CLASS: Record<Direction, string> = { rising: "up", easing: "down", steady: "steady", unclear: "unclear" };
const DIR_WORD: Record<Direction, string> = { rising: "Escalating", easing: "Easing", steady: "Steady", unclear: "Unclear" };
const DIR_GLYPH = { rising: "up", easing: "down", steady: "steady", unclear: "unclear" } as const;

/** Escalating / steady / easing as a coloured mark. `label` shows the word beside it; without it the word is read by screen readers only. */
export function DirMark({ direction, label = false }: { direction: Direction; label?: boolean }) {
  return (
    <span className={`vl-dir vl-dir-${DIR_CLASS[direction]}`}>
      <Glyph name={DIR_GLYPH[direction]} size={label ? 12 : 14} />
      {label ? <span className="vl-dir-word">{DIR_WORD[direction]}</span> : <span className="vl-sr">{DIR_WORD[direction]}</span>}
    </span>
  );
}

/** A bar on a shared 0..1 scale (`share`), tinted by `--tone` (defaults to the accent). */
export function HeatBar({ share, label }: { share: number; label: string }) {
  const pct = Math.round(Math.min(1, Math.max(0, share)) * 100);
  return (
    <span className="vl-bar" role="img" aria-label={`${label}: ${pct} out of 100 on this screen's scale`}>
      <span className="vl-bar-fill" style={{ width: `${pct > 0 ? Math.max(pct, 4) : 0}%` }} />
    </span>
  );
}

/** A hairline line for a short series (e.g. headlines per day), the latest reading marked by a small accent square. Needs at least two
 *  points; draws nothing otherwise. Scales to its own min..max, so it shows shape, not size. */
export function Spark({ values, label }: { values: number[]; label: string }) {
  if (values.length < 2) return null;
  const W = 64;
  const H = 20;
  const lo = Math.min(...values);
  const span = Math.max(...values) - lo || 1;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * (W - 3) + 1.5, H - 2 - ((v - lo) / span) * (H - 4)] as const);
  const last = pts[pts.length - 1];
  return (
    <svg className="vl-spark" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      <polyline points={pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ")} />
      <rect x={last[0] - 1.5} y={last[1] - 1.5} width={3} height={3} />
    </svg>
  );
}

/** A 2px full-height bar in the direction colour: the quietest direction mark for ranked rows. The word is read by screen readers only. */
export function DirTick({ direction }: { direction: Direction }) {
  return (
    <span className={`vl-tick vl-tick-${DIR_CLASS[direction]}`}>
      <span className="vl-sr">{DIR_WORD[direction]}</span>
    </span>
  );
}

/** A signed change ("+4.2%", "-3 pts"), coloured by its sign unless `neutral`. The sign itself carries the meaning. */
export function Delta({ text, sign, neutral = false }: { text: string; sign: number; neutral?: boolean }) {
  const cls = neutral || sign === 0 ? "" : sign > 0 ? " vl-delta-up" : " vl-delta-down";
  return <span className={`vl-delta${cls}`}>{text}</span>;
}

/** A count as a big numeral with a tiny label beneath. */
export function Numeral({ n, label }: { n: string | number; label: string }) {
  return (
    <span className="vl-numeral">
      <span className="vl-num">{n}</span>
      <span className="vl-label">{label}</span>
    </span>
  );
}

export function StatusDot({ state, label }: { state: "fresh" | "aging" | "stale"; label: string }) {
  return <span className={`vl-dot vl-dot-${state}`} role="img" aria-label={label} />;
}
