import { COVERAGE_DISPLAY, type Band, type Coverage } from "@/lib/intel";

// Hand-written SVG micro-visuals for the Intelligence desk. Pure server components; colors come
// from CSS (currentColor / intel- classes) so they follow the light/dark display.

export function Sparkline({ points, band, label }: { points: number[]; band: Band; label: string }) {
  const W = 96;
  const H = 26;
  const pad = 3;
  const y = (v: number) => pad + (1 - Math.min(100, Math.max(0, v)) / 100) * (H - pad * 2);
  let body: React.ReactNode;
  if (points.length === 0) {
    body = <line x1={pad} x2={W - pad} y1={H / 2} y2={H / 2} className="intel-spark-empty" />;
  } else if (points.length === 1) {
    body = <circle cx={W - pad} cy={y(points[0])} r={2.5} className="intel-spark-dot" />;
  } else {
    const step = (W - pad * 2) / (points.length - 1);
    const xy = points.map((v, i) => [pad + i * step, y(v)] as const);
    const d = xy.map(([x, yy], i) => `${i ? "L" : "M"}${x.toFixed(1)},${yy.toFixed(1)}`).join(" ");
    const last = xy[xy.length - 1];
    body = (
      <>
        <path d={d} className="intel-spark-line" />
        <circle cx={last[0]} cy={last[1]} r={2.5} className="intel-spark-dot" />
      </>
    );
  }
  return (
    <svg className={`intel-spark intel-band-${band}`} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} preserveAspectRatio="none">
      {body}
    </svg>
  );
}

/** Mini daily-count bars. */
export function DayBars({ series, label }: { series: { day: string; count: number }[]; label: string }) {
  const W = 112;
  const H = 26;
  if (series.length === 0) return <span className="intel-muted">—</span>;
  const max = Math.max(1, ...series.map((s) => s.count));
  const slot = W / series.length;
  const bw = Math.max(1, slot - 1.5);
  return (
    <svg className="intel-bars" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      <line x1={0} x2={W} y1={H - 0.5} y2={H - 0.5} className="intel-bars-base" />
      {series.map((s, i) => {
        const h = s.count > 0 ? Math.max(1.5, (s.count / max) * (H - 3)) : 0;
        return <rect key={i} x={i * slot} y={H - 1 - h} width={bw} height={h} className="intel-bars-bar" />;
      })}
    </svg>
  );
}

export function HeatBar({ heat }: { heat: number }) {
  const pct = Math.max(0, Math.min(100, heat <= 1 ? heat * 100 : heat));
  return (
    <span className="intel-heat" role="img" aria-label={`Share of headlines: ${Math.round(pct)} of 100`}>
      <span className="intel-heat-fill" style={{ width: `${pct}%` }} />
    </span>
  );
}

// ---- actor network --------------------------------------------------------------------------
export const RELATION_KINDS: Record<string, string> = {
  strikes: "Strikes",
  sabotage: "Sabotage",
  coerces: "Coerces",
  sanctions: "Sanctions",
  supports: "Supports",
  negotiates: "Negotiates",
  deters: "Deters",
  other: "Other",
};
const kindOf = (k: string) => (k in RELATION_KINDS ? k : "other");

type Rel = { source: string; target: string; kind: string; note: string; date: string };

export function ActorMap({ relations }: { relations: Rel[] }) {
  const actors = Array.from(new Set(relations.flatMap((r) => [r.source, r.target])));
  const n = actors.length;
  const W = 640;
  const H = 440;
  const cx = W / 2;
  const cy = H / 2;
  const R = n <= 2 ? 120 : Math.min(150, 70 + n * 14);
  const pos = new Map<string, { x: number; y: number; a: number }>();
  actors.forEach((name, i) => {
    const a = (i / n) * Math.PI * 2 - Math.PI / 2;
    pos.set(name, { x: cx + Math.cos(a) * R * 1.45, y: cy + Math.sin(a) * R, a });
  });
  const usedKinds = Array.from(new Set(relations.map((r) => kindOf(r.kind))));
  const NODE_R = 7;

  return (
    <figure className="intel-map">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Network of relations between actors. A table with the same information follows." className="intel-map-svg">
        <defs>
          {usedKinds.map((k) => (
            <marker key={k} id={`intel-arrow-${k}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse" className={`intel-k-${k}`}>
              <path d="M0,1 L9,5 L0,9 z" fill="currentColor" />
            </marker>
          ))}
        </defs>
        {relations.map((r, i) => {
          const s = pos.get(r.source)!;
          const t = pos.get(r.target)!;
          const k = kindOf(r.kind);
          if (r.source === r.target) {
            // self-loop: small arc outside the node
            const ox = Math.cos(s.a) * 22;
            const oy = Math.sin(s.a) * 22;
            return (
              <circle key={i} cx={s.x + ox} cy={s.y + oy} r={11} fill="none" className={`intel-edge intel-k-${k}`} markerEnd={`url(#intel-arrow-${k})`} />
            );
          }
          const dx = t.x - s.x;
          const dy = t.y - s.y;
          const len = Math.hypot(dx, dy) || 1;
          const ux = dx / len;
          const uy = dy / len;
          // curve parallel/opposite edges apart so they do not overlap
          const sameDir = relations.slice(0, i).filter((q) => q.source === r.source && q.target === r.target).length;
          const reverse = relations.some((q) => q.source === r.target && q.target === r.source);
          const bend = (reverse ? 18 : 0) + sameDir * 16;
          const sx = s.x + ux * NODE_R;
          const sy = s.y + uy * NODE_R;
          const ex = t.x - ux * (NODE_R + 5);
          const ey = t.y - uy * (NODE_R + 5);
          const mx = (sx + ex) / 2 - uy * bend;
          const my = (sy + ey) / 2 + ux * bend;
          return (
            <path
              key={i}
              d={`M${sx.toFixed(1)},${sy.toFixed(1)} Q${mx.toFixed(1)},${my.toFixed(1)} ${ex.toFixed(1)},${ey.toFixed(1)}`}
              fill="none"
              className={`intel-edge intel-k-${k}`}
              markerEnd={`url(#intel-arrow-${k})`}
            >
              <title>{`${r.source} ${RELATION_KINDS[k].toLowerCase()} ${r.target}${r.note ? ` — ${r.note}` : ""}`}</title>
            </path>
          );
        })}
        {actors.map((name) => {
          const p = pos.get(name)!;
          const cos = Math.cos(p.a);
          const anchor = Math.abs(cos) < 0.2 ? "middle" : cos > 0 ? "start" : "end";
          const lx = p.x + (anchor === "middle" ? 0 : cos > 0 ? 13 : -13);
          const ly = anchor === "middle" ? p.y + (Math.sin(p.a) > 0 ? 24 : -14) : p.y + 4;
          return (
            <g key={name}>
              <circle cx={p.x} cy={p.y} r={NODE_R} className="intel-node" />
              <text x={lx} y={ly} textAnchor={anchor} className="intel-node-label">
                {name.length > 26 ? `${name.slice(0, 25)}…` : name}
              </text>
            </g>
          );
        })}
      </svg>
      <ul className="intel-legend" aria-label="Edge colors">
        {usedKinds.map((k) => (
          <li key={k}>
            <svg width="22" height="8" aria-hidden="true" className={`intel-k-${k}`}>
              <line x1="0" x2="22" y1="4" y2="4" stroke="currentColor" strokeWidth="2" />
            </svg>
            {RELATION_KINDS[k]}
          </li>
        ))}
      </ul>
    </figure>
  );
}

// ---- escalation chips -----------------------------------------------------------------------
const DIR_GLYPH: Record<string, string> = { rising: "▲", steady: "◆", easing: "▼", unclear: "?" };
const DIR_CLASS: Record<string, string> = { rising: "severe", steady: "elevated", easing: "calm", unclear: "unassessed" };

/** Escalation is the situation itself (not coverage, not Pulse severity). `labelled` spells that out. */
export function EscalationChips({ direction, pace, labelled = false }: { direction: string; pace: string; labelled?: boolean }) {
  if (!direction && !pace) return null;
  return (
    <span className="intel-chips" title={labelled ? "Is the situation itself getting worse, steadier or easing" : undefined}>
      {labelled && <span className="intel-micro intel-chips-label">Escalation:</span>}
      {direction && (
        <span className={`intel-chip intel-band-${DIR_CLASS[direction] ?? "unassessed"}`}>
          {DIR_GLYPH[direction] ?? "·"} {direction}
        </span>
      )}
      {pace && <span className="intel-chip intel-band-unassessed">{pace} pace</span>}
    </span>
  );
}

/** Thin horizontal probability bar (1-99). */
export function ProbBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <span className="intel-prob-bar" role="img" aria-label={`${Math.round(pct)} percent`}>
      <span className="intel-prob-fill" style={{ width: `${pct}%` }} />
    </span>
  );
}

/** Calibration: forecast probability (x) vs how often it happened (y); diagonal = perfectly calibrated. */
export function CalibrationChart({ buckets }: { buckets: { range: string; count: number; hit_rate: number }[] }) {
  const W = 280;
  const H = 240;
  const L = 34;
  const B = 28;
  const T = 8;
  const R = 10;
  const px = (v: number) => L + (v / 100) * (W - L - R);
  const py = (v: number) => T + (1 - v / 100) * (H - T - B);
  const maxCount = Math.max(1, ...buckets.map((b) => b.count));
  const ticks = [0, 25, 50, 75, 100];
  const pts = buckets.map((b) => {
    const m = b.range.match(/^(\d+)\D+(\d+)/);
    const lo = m ? Number(m[1]) : parseInt(b.range, 10);
    const hi = m ? Number(m[2]) : lo + 9;
    const rate = b.hit_rate * 100; // backend sends a 0-1 fraction
    return { ...b, x: (lo + hi + 1) / 2, y: Math.max(0, Math.min(100, rate)), r: 3 + 5 * Math.sqrt(b.count / maxCount) };
  });
  return (
    <svg className="intel-calib" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Calibration: how often forecasts at each probability actually happened">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={px(t)} x2={px(t)} y1={T} y2={H - B} className="intel-calib-grid" />
          <line x1={L} x2={W - R} y1={py(t)} y2={py(t)} className="intel-calib-grid" />
          <text x={px(t)} y={H - B + 13} textAnchor="middle" className="intel-calib-tick">{t}</text>
          <text x={L - 5} y={py(t) + 3} textAnchor="end" className="intel-calib-tick">{t}</text>
        </g>
      ))}
      <line x1={px(0)} y1={py(0)} x2={px(100)} y2={py(100)} className="intel-calib-diag" />
      {pts.map((p) => (
        <circle key={p.range} cx={px(p.x)} cy={py(p.y)} r={p.r} className="intel-calib-dot">
          <title>{`Forecast ${p.range}%: happened ${Math.round(p.y)}% of the time (${p.count} forecast${p.count === 1 ? "" : "s"})`}</title>
        </circle>
      ))}
      <text x={(L + W - R) / 2} y={H - 3} textAnchor="middle" className="intel-calib-axis">What we forecast (%)</text>
      <text transform={`translate(9 ${(T + H - B) / 2}) rotate(-90)`} textAnchor="middle" className="intel-calib-axis">How often it happened (%)</text>
    </svg>
  );
}

/** Coverage: how much of the world’s headlines a theater takes. Neutral colour on purpose: never a band colour. */
export function CoverageTag({ coverage, bare = false }: { coverage: Coverage; bare?: boolean }) {
  const c = COVERAGE_DISPLAY[coverage];
  return (
    <span className="intel-cov" title="Share of today’s headlines about this theater">
      {!bare && <span className="intel-micro">Coverage </span>}
      <span aria-hidden="true">{c.glyph}</span> {c.label}
    </span>
  );
}
