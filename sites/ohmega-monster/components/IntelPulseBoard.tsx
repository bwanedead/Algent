import { BAND_LABEL, maxBand, type Situation } from "@/lib/intel";

import PulseCard, { baseOf } from "./PulseCard";

/** DOM id for a Situation block (deep links and the /pulses jump bar). */
export const situationAnchor = (id: string) => `sit-${id.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;

const WATCH_DIR = { up: "▲ rising", down: "▼ falling", either: "◆ either way" } as const;

export default function PulseBoard({ situations }: { situations: Situation[] }) {
  if (situations.length === 0) return <p className="intel-empty">No Pulses published yet.</p>;
  return (
    <div className="intel-situations">
      {situations.map((s) => {
        const top = maxBand(s.pulses);
        const assessed = s.pulses.filter((p) => p.position !== null).length;
        return (
          <section key={s.id} id={situationAnchor(s.id)} className={`intel-situation intel-frame intel-band-${top}`} aria-label={s.title}>
            <header className="intel-situation-head">
              <div className="intel-frame-band">
                <h3>{s.title}</h3>
                {s.domain && <span className="intel-micro">{s.domain}</span>}
                <span className="intel-frame-meta">
                  {top !== "unassessed" && (
                    <span className={`intel-chip intel-band-${top}`} title="Most severe reading in this Situation">
                      Max · {BAND_LABEL[top]}
                    </span>
                  )}
                  <span className="intel-micro">
                    {assessed}/{s.pulses.length} Pulses assessed
                  </span>
                </span>
              </div>
              {s.summary && <SituationSummary text={s.summary} />}
            </header>
            <div className="intel-frame-body">
              {s.pulses.length > 0 ? (
                <div className="intel-pulse-grid">
                  {s.pulses.map((p) => (
                    <PulseCard key={p.id} base={baseOf(p)} full={p} anchor />
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
            </div>
          </section>
        );
      })}
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
