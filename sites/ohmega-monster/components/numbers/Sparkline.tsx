// THE sparkline of the site's numbers layer: one line, one end dot, no axes. Each series is drawn on its own
// vertical range (shape, not magnitude: the number beside it carries the magnitude). `hot` is the accent and
// means "unusual / changed"; everything else is neutral. Pure SVG, so it renders on the server.

type Props = { values: number[]; label: string; hot?: boolean; large?: boolean };

const SMALL = { w: 84, h: 24 };
const LARGE = { w: 360, h: 80 };
const PAD = 2.5;

export default function Sparkline({ values, label, hot = false, large = false }: Props) {
  if (values.length < 2) return null;
  const { w, h } = large ? LARGE : SMALL;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const x = (i: number) => PAD + (i / (values.length - 1)) * (w - 2 * PAD);
  const y = (v: number) => (hi === lo ? h / 2 : h - PAD - ((v - lo) / span) * (h - 2 * PAD));
  const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const last = values.length - 1;
  return (
    <svg className={`num-spark${hot ? " is-hot" : ""}${large ? " is-large" : ""}`} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={label}>
      <polyline points={pts} fill="none" className="num-spark-line" vectorEffect="non-scaling-stroke" />
      <circle cx={x(last)} cy={y(values[last])} r={large ? 3 : 2.2} className="num-spark-dot" />
    </svg>
  );
}
