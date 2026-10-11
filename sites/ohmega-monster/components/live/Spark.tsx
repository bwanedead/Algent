// A plain sparkline: one line, an optional shaded band (the range of earlier years at the same dates) and a dot on the latest
// value. No axes, no ticks: the number beside it carries the reading. Server- and client-safe (pure SVG).

type Props = {
  values: (number | null)[];
  band?: ([number, number] | null)[];
  width?: number;
  height?: number;
  label: string;
};

export default function Spark({ values, band, width = 140, height = 36, label }: Props) {
  const nums = [...values, ...(band ?? []).flatMap((b) => (b ? b : []))].filter((v): v is number => v !== null);
  if (nums.length < 2) return null;
  const lo = Math.min(...nums);
  const hi = Math.max(...nums);
  const span = hi - lo || 1;
  const n = values.length;
  const pad = 3;
  const x = (i: number) => pad + (i / Math.max(1, n - 1)) * (width - 2 * pad);
  const y = (v: number) => height - pad - ((v - lo) / span) * (height - 2 * pad);

  const segments: string[] = [];
  let cur = "";
  values.forEach((v, i) => {
    if (v === null) {
      if (cur) segments.push(cur);
      cur = "";
    } else cur += `${cur ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`;
  });
  if (cur) segments.push(cur);

  let bandPath = "";
  if (band) {
    const idx = band.map((b, i) => (b ? i : -1)).filter((i) => i >= 0);
    if (idx.length > 1) {
      const up = idx.map((i, k) => `${k ? "L" : "M"}${x(i).toFixed(1)} ${y((band[i] as [number, number])[1]).toFixed(1)}`).join("");
      const down = [...idx].reverse().map((i) => `L${x(i).toFixed(1)} ${y((band[i] as [number, number])[0]).toFixed(1)}`).join("");
      bandPath = `${up}${down}Z`;
    }
  }
  const lastIdx = values.map((v) => v !== null).lastIndexOf(true);
  const last = lastIdx >= 0 ? (values[lastIdx] as number) : null;

  return (
    <svg className="live-spark" viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={label}>
      {bandPath && <path d={bandPath} className="live-spark-band" />}
      {segments.map((d, i) => (
        <path key={i} d={d} className="live-spark-line" />
      ))}
      {last !== null && <circle cx={x(lastIdx)} cy={y(last)} r={2.4} className="live-spark-dot" />}
    </svg>
  );
}
