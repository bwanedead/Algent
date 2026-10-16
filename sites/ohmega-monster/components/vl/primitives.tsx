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
      <Glyph name={DIR_GLYPH[direction]} size={label ? 12 : 16} />
      {label ? <span className="vl-dir-word">{DIR_WORD[direction]}</span> : <span className="vl-sr">{DIR_WORD[direction]}</span>}
    </span>
  );
}

/** A bar on a shared 0..1 scale (`share`), tinted by `--tone` (defaults to the accent). */
export function HeatBar({ share, label }: { share: number; label: string }) {
  const pct = Math.round(Math.min(1, Math.max(0, share)) * 100);
  return (
    <span className="vl-bar" role="img" aria-label={`${label}: ${pct} out of 100 on this screen's scale`}>
      <span className="vl-bar-fill" style={{ width: `${pct > 0 ? Math.max(pct, 6) : 0}%` }} />
    </span>
  );
}

/** Bars for a short series (e.g. headlines per day). Needs at least two points; draws nothing otherwise. */
export function Spark({ values, label }: { values: number[]; label: string }) {
  if (values.length < 2) return null;
  const W = 60;
  const H = 20;
  const max = Math.max(1, ...values);
  const slot = W / values.length;
  return (
    <svg className="vl-spark" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} preserveAspectRatio="none">
      {values.map((v, i) => {
        const h = v > 0 ? Math.max(2, (v / max) * (H - 1)) : 0;
        return <rect key={i} x={i * slot + 0.5} y={H - h} width={Math.max(1, slot - 2)} height={h} rx={1} className={i === values.length - 1 ? "vl-spark-now" : undefined} />;
      })}
    </svg>
  );
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
