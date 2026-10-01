import type { Metadata } from "next";
import Link from "next/link";

import PulseBoard from "@/components/IntelPulseBoard";
import { CalibrationChart, DayBars, EscalationChips, HeatBar } from "@/components/IntelViz";
import { fmtUtc, latestSnapshot } from "@/lib/intel";

export const metadata: Metadata = {
  title: "Intelligence",
  description: "Pulses, Situations, Theaters and Briefs — a running read of where the world is moving.",
};

const TREND = {
  heating: { glyph: "▲", cls: "severe", label: "Heating" },
  steady: { glyph: "◆", cls: "elevated", label: "Steady" },
  cooling: { glyph: "▼", cls: "calm", label: "Cooling" },
  new: { glyph: "●", cls: "unassessed", label: "New" },
} as const;

const OUTCOME = {
  yes: { cls: "calm", label: "Happened" },
  no: { cls: "elevated", label: "Didn’t happen" },
  void: { cls: "unassessed", label: "Void" },
} as const;

export default function IntelPage() {
  const snap = latestSnapshot();
  const situations = snap?.situations ?? [];
  const pulses = situations.flatMap((s) => s.pulses);
  const assessed = pulses.filter((p) => p.position !== null).length;
  const theaters = [...(snap?.theaters ?? [])].sort((a, b) => b.heat - a.heat);
  const heating = theaters.filter((t) => t.trend === "heating").length;
  const briefs = [...(snap?.briefs ?? [])].sort((a, b) => b.as_of.localeCompare(a.as_of));

  return (
    <div className="intel-page">
      <div className="intel-strip" role="group" aria-label="Status">
        <span className="intel-strip-title">Intelligence</span>
        <span className="intel-strip-item">
          <span className="intel-micro">As of</span> {snap?.built_at ? fmtUtc(snap.built_at) : "—"}
        </span>
        <span className="intel-strip-item">
          <b className="intel-num-sm">{situations.length}</b> <span className="intel-micro">Situations</span>
        </span>
        <span className="intel-strip-item">
          <b className="intel-num-sm">{assessed}</b>
          <span className="intel-micro">/{pulses.length} Pulses assessed</span>
        </span>
        <span className="intel-strip-item">
          <b className="intel-num-sm">{heating}</b> <span className="intel-micro">Theaters heating</span>
        </span>
        <span className="intel-strip-item">
          <b className="intel-num-sm">{briefs.length}</b> <span className="intel-micro">Briefs</span>
        </span>
      </div>

      <p className="intel-note daily-xlink">
        <Link href="/geopolitics">Geopolitics — the daily report →</Link>
      </p>

      {!snap && <p className="intel-empty">No intelligence has been published yet. Check back soon.</p>}

      {snap && (
        <>
          <section className="intel-section" aria-labelledby="intel-pulses">
            <div className="intel-section-head">
              <h2 id="intel-pulses">Pulses</h2>
              <span className="intel-trust" title="Pulses are new. Treat every reading as provisional.">
                Early readings — still calibrating
              </span>
            </div>
            <p className="intel-note">Each Pulse reads 0–100 on one question. Open a tile for the question, both ends of the scale, and the reasoning.</p>
            <PulseBoard situations={situations} />
          </section>

          <section className="intel-section" aria-labelledby="intel-theaters">
            <div className="intel-section-head">
              <h2 id="intel-theaters">Theaters</h2>
              <span className="intel-micro">Emerging hotspots, hottest first</span>
            </div>
            {theaters.length === 0 ? (
              <p className="intel-empty">No Theaters flagged right now.</p>
            ) : (
              <div className="intel-table-wrap">
                <table className="intel-table">
                  <thead>
                    <tr>
                      <th scope="col">Theater</th>
                      <th scope="col">Trend</th>
                      <th scope="col">Heat</th>
                      <th scope="col">Daily reports</th>
                      <th scope="col" className="intel-r">Recent / prior</th>
                      <th scope="col"><span className="intel-sr">Brief</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {theaters.map((t) => {
                      const tr = TREND[t.trend];
                      return (
                        <tr key={t.id}>
                          <th scope="row">
                            <span className="intel-strong">{t.name}</span>
                            {t.domain && <span className="intel-micro"> {t.domain}</span>}
                            {t.why && <span className="intel-why">{t.why}</span>}
                          </th>
                          <td>
                            <span className={`intel-trend intel-band-${tr.cls}`} title={tr.label}>
                              {tr.glyph} {tr.label}
                            </span>
                          </td>
                          <td>
                            <HeatBar heat={t.heat} />
                          </td>
                          <td>
                            <DayBars series={t.series} label={`${t.name}: daily report counts`} />
                          </td>
                          <td className="intel-r intel-tab">
                            {t.recent} / {t.prior}
                          </td>
                          <td className="intel-r">{t.brief ? <Link href={`/intel/briefs/${t.brief}`}>Brief →</Link> : null}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="intel-section" aria-labelledby="intel-briefs">
            <div className="intel-section-head">
              <h2 id="intel-briefs">Briefs</h2>
              <span className="intel-micro">Latest first</span>
            </div>
            {briefs.length === 0 ? (
              <p className="intel-empty">No Briefs published yet.</p>
            ) : (
              <ul className="intel-brief-list">
                {briefs.map((b) => (
                  <li key={b.slug}>
                    <Link href={`/intel/briefs/${b.slug}`}>
                      <span className="intel-brief-meta">
                        <time className="intel-micro">{b.as_of.slice(0, 10)}</time>
                        <EscalationChips direction={b.direction} pace={b.pace} />
                      </span>
                      <span className="intel-brief-body">
                        <strong>{b.title}</strong>
                        {b.theater_name && <span className="intel-micro"> {b.theater_name}</span>}
                        {b.bottom_line && <span className="intel-brief-bl">{b.bottom_line}</span>}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="intel-section" aria-labelledby="intel-track">
            <div className="intel-section-head">
              <h2 id="intel-track">Track record</h2>
              <span className="intel-micro">Forecasts are scored publicly when they resolve</span>
            </div>
            <div className="intel-strip intel-score" role="group" aria-label="Scorecard">
              <span className="intel-strip-item">
                <b className="intel-num-sm">{snap.forecasts.scorecard.resolved}</b> <span className="intel-micro">Resolved</span>
              </span>
              <span className="intel-strip-item">
                <b className="intel-num-sm">{snap.forecasts.scorecard.open}</b> <span className="intel-micro">Open</span>
              </span>
              <span className="intel-strip-item">
                <span className="intel-micro">Brier score</span> <b className="intel-num-sm">{snap.forecasts.scorecard.brier !== null ? snap.forecasts.scorecard.brier.toFixed(3) : "—"}</b>
              </span>
            </div>
            <p className="intel-note">
              {snap.forecasts.scorecard.resolved === 0 && snap.forecasts.scorecard.brier === null
                ? "No forecasts resolved yet — the record starts now. "
                : ""}
              Brier score: 0 is perfect, 0.25 is a coin flip — lower is better.
            </p>

            {snap.forecasts.scorecard.calibration.length > 0 && snap.forecasts.scorecard.resolved > 0 && (
              <figure className="intel-calib-fig">
                <CalibrationChart buckets={snap.forecasts.scorecard.calibration} />
                <figcaption className="intel-note">
                  Calibration: when we said 70%, it should happen about 70% of the time. Dots on the diagonal mean we are well calibrated; bigger dots are more forecasts.
                </figcaption>
              </figure>
            )}

            <h3 className="intel-sub">Due soonest</h3>
            {snap.forecasts.open.length === 0 ? (
              <p className="intel-empty">No open forecasts.</p>
            ) : (
              <div className="intel-table-wrap">
                <table className="intel-table intel-fc-table">
                  <thead>
                    <tr>
                      <th scope="col" className="intel-r">Chance</th>
                      <th scope="col">Forecast</th>
                      <th scope="col">By</th>
                      <th scope="col"><span className="intel-sr">Brief</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {snap.forecasts.open.map((o, i) => (
                      <tr key={i}>
                        <td className="intel-r intel-tab intel-strong">{o.probability}%</td>
                        <td>
                          {o.statement}
                          {o.theater_name && <span className="intel-why">{o.theater_name}</span>}
                        </td>
                        <td className="intel-tab">{o.horizon}</td>
                        <td>{/^[\w.-]+$/.test(o.brief_slug) ? <Link href={`/intel/briefs/${o.brief_slug}`}>Brief →</Link> : null}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {snap.forecasts.resolved.length > 0 && (
              <>
                <h3 className="intel-sub">Recently resolved</h3>
                <ul className="intel-resolved">
                  {snap.forecasts.resolved.map((r, i) => {
                    const o = OUTCOME[r.outcome];
                    return (
                      <li key={i}>
                        <span className={`intel-chip intel-band-${o.cls}`}>{o.label}</span>
                        <div>
                          <p>
                            <span className="intel-strong intel-tab">{r.probability}%</span> {r.statement}
                          </p>
                          {r.evidence && <p className="intel-muted">{r.evidence}</p>}
                          {r.resolved_at && <p className="intel-micro">Resolved {r.resolved_at.slice(0, 10)}</p>}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}
