import { BAND_LABEL, type Pulse, type Situation } from "@/lib/intel";

import { Sparkline } from "./IntelViz";

export function BandChip({ band }: { band: Pulse["band"] }) {
  return <span className={`intel-chip intel-band-${band}`}>{BAND_LABEL[band]}</span>;
}

function fmtDelta(v: number | null): string {
  if (v === null) return "—";
  const r = Math.round(v * 10) / 10;
  if (r === 0) return "◆ 0";
  return `${r > 0 ? "▲ +" : "▼ −"}${Math.abs(r)}`;
}

function PulseTile({ p }: { p: Pulse }) {
  const assessed = p.position !== null;
  const d7 = p.velocity_7d;
  const dirClass = d7 === null || Math.round(d7 * 10) === 0 ? "flat" : d7 > 0 ? "up" : "down";
  return (
    <details id={`pulse-${p.id}`} className={`intel-pulse intel-band-${p.band}`}>
      <summary>
        <span className="intel-pulse-name">{p.name}</span>
        <span className="intel-pulse-main">
          <span className={assessed ? "intel-num" : "intel-num intel-muted"}>{assessed ? Math.round(p.position as number) : "—"}</span>
          <BandChip band={p.band} />
        </span>
        <Sparkline points={p.history.map((h) => h.position)} band={p.band} label={`${p.name}: ${p.history.length} readings`} />
        <span className="intel-pulse-foot">
          <span className={`intel-delta intel-delta-${dirClass}`} title="Change over 7 days">
            {fmtDelta(d7)}
            <span className="intel-micro"> 7d</span>
          </span>
          <span className="intel-micro">{p.confidence ? `${p.confidence} confidence` : "confidence n/a"}</span>
        </span>
      </summary>
      <div className="intel-pulse-body">
        {p.question && <p className="intel-pulse-q">{p.question}</p>}
        {(p.low_end || p.high_end) && (
          <dl className="intel-ends">
            <div>
              <dt>0</dt>
              <dd>{p.low_end || "—"}</dd>
            </div>
            <div>
              <dt>100</dt>
              <dd>{p.high_end || "—"}</dd>
            </div>
          </dl>
        )}
        {p.rationale ? <p className="intel-rationale">{p.rationale}</p> : <p className="intel-muted">No reading yet.</p>}
        <p className="intel-micro">
          {p.last_assessed && <>Assessed {p.last_assessed.slice(0, 10)}</>}
          {p.evidence_through && <> · evidence through {p.evidence_through.slice(0, 10)}</>}
          {p.velocity_30d !== null && <> · 30d {fmtDelta(p.velocity_30d)}</>}
        </p>
      </div>
    </details>
  );
}

const WATCH_DIR = { up: "▲ rising", down: "▼ falling", either: "◆ either way" } as const;

export default function PulseBoard({ situations }: { situations: Situation[] }) {
  if (situations.length === 0) return <p className="intel-empty">No Pulses published yet.</p>;
  return (
    <div className="intel-situations">
      {situations.map((s) => (
        <section key={s.id} className="intel-situation" aria-label={s.title}>
          <header className="intel-situation-head">
            <h3>{s.title}</h3>
            {s.domain && <span className="intel-micro">{s.domain}</span>}
            {s.summary && <SituationSummary text={s.summary} />}
          </header>
          {s.pulses.length > 0 ? (
            <div className="intel-pulse-grid">
              {s.pulses.map((p) => (
                <PulseTile key={p.id} p={p} />
              ))}
            </div>
          ) : (
            <p className="intel-muted">No Pulses in this Situation yet.</p>
          )}
          {s.watches.length > 0 && (
            <div className="intel-warnings">
              <h4 className="intel-micro">Warning signs</h4>
              <ul>
                {s.watches.map((w, i) => (
                  <li key={i}>
                    <span className="intel-warn-dir">{WATCH_DIR[w.direction]}</span>
                    <span>
                      {w.condition}
                      {w.why && <span className="intel-muted"> — {w.why}</span>}
                    </span>
                    {w.horizon && <span className="intel-micro">{w.horizon}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      ))}
    </div>
  );
}

// The lead sentence stays visible; the rest folds away so the board stays scannable, not a wall.
function SituationSummary({ text }: { text: string }) {
  const cut = text.search(/[.!?]\s/);
  if (cut < 0 || cut > text.length - 40) return <p>{text}</p>;
  return (
    <details className="intel-sit-summary">
      <summary>{text.slice(0, cut + 1)}</summary>
      <p>{text.slice(cut + 2)}</p>
    </details>
  );
}
