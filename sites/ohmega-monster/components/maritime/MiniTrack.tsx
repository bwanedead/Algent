// A tiny, dependency-free picture of where a vessel was: its evidence points joined in order (hollow dot = first, filled = last). Equirectangular with
// the longitude scaled by cos(latitude) so shapes are not stretched. No axes or labels; the words beside it carry the numbers. Client-safe.

const W = 150;
const H = 60;
const PAD = 6;

export default function MiniTrack({ points, label, color = "currentColor" }: { points: [number, number][]; label: string; color?: string }) {
  if (points.length === 0) return null;
  const midLat = points.reduce((s, p) => s + p[1], 0) / points.length;
  const k = Math.max(0.2, Math.cos((midLat * Math.PI) / 180));
  const xs = points.map((p) => p[0] * k);
  const ys = points.map((p) => p[1]);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  const span = Math.max(x1 - x0, y1 - y0, 1e-6);
  const scale = (Math.min(W, H) - 2 * PAD) / span;
  const cx = (W - (x1 - x0) * scale) / 2;
  const cy = (H - (y1 - y0) * scale) / 2;
  const at = (i: number): [number, number] => [cx + (xs[i] - x0) * scale, H - (cy + (ys[i] - y0) * scale)];
  const pts = points.map((_, i) => at(i));
  const [first, last] = [pts[0], pts[pts.length - 1]];
  return (
    <svg className="mb-track" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={label}>
      <rect x="0.5" y="0.5" width={W - 1} height={H - 1} fill="none" stroke="var(--rule)" />
      {pts.length > 1 && <polyline points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke={color} strokeWidth="1.4" strokeDasharray="3 2" />}
      <circle cx={first[0]} cy={first[1]} r="3" fill="var(--panel)" stroke={color} strokeWidth="1.4" />
      {pts.length > 1 && <circle cx={last[0]} cy={last[1]} r="3" fill={color} />}
    </svg>
  );
}
