import Link from "next/link";

import type { Daily, DailyChangeKind, DailyDevelopment, DailyStatement, DailyTheater } from "@/lib/daily";
import { fmtDay } from "@/lib/daily";
import { findPulse, fmtUtc, latestSnapshot, maxBand, type Snapshot } from "@/lib/intel";

import { CoverageSpark, DevTimeline, KeyFigureTiles, mapIndexBase, SourceLink, TheaterMapSlot } from "./DailyVisuals";
import { CoverageTag, EscalationChips, HeatBar } from "./IntelViz";
import PulseCard from "./PulseCard";
import { SpectrumLegend } from "./PulseSpectrum";

const CHANGE: Record<DailyChangeKind, { glyph: string; cls: string; label: string }> = {
  escalated: { glyph: "▲", cls: "severe", label: "Escalated" },
  eased: { glyph: "▼", cls: "calm", label: "Eased" },
  new: { glyph: "●", cls: "elevated", label: "New" },
  resolved: { glyph: "✓", cls: "calm", label: "Resolved" },
  unchanged: { glyph: "=", cls: "unassessed", label: "Unchanged" },
};

const anchorId = (t: DailyTheater, i: number) => `theater-${i}-${t.theater_id.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;

function Statement({ s }: { s: DailyStatement }) {
  const attribution = (
    <figcaption className="daily-quote-cap">
      <span className="intel-strong">{s.who || "Unattributed"}</span>
      {s.role && <span className="intel-muted">, {s.role}</span>}
      {s.when && <span className="intel-micro"> · {s.when}</span>}
      {s.source && (
        <>
          {" "}
          <SourceLink url={s.source} />
        </>
      )}
    </figcaption>
  );
  if (s.quote) {
    return (
      <figure className="daily-quote">
        <blockquote>
          <p>“{s.said}”</p>
        </blockquote>
        {attribution}
      </figure>
    );
  }
  return (
    <figure className="daily-quote daily-quote-para">
      <p>
        <span className="intel-strong">{s.who || "A source"}</span> said that {s.said}
      </p>
      {attribution}
    </figure>
  );
}

/** `n` is the development’s number when the map marks it. */
function Development({ d, n }: { d: DailyDevelopment; n: number | null }) {
  const verified = d.verification === "researched";
  const where = d.where || [d.place?.name, d.place?.country].filter(Boolean).join(", ");
  return (
    <li className="daily-dev">
      <div className="daily-dev-head">
        <h4>
          {n !== null && <span className={`daily-map-n ${verified ? "is-solid" : "is-hollow"}`} title="Marked on the map">{n}</span>}
          {d.headline}
        </h4>
        <span className={`intel-chip intel-band-${verified ? "calm" : "elevated"}`} title={verified ? "Checked against sources we read" : "Reported by outlets; not independently checked"}>
          {verified ? "Researched" : "Reported — unverified"}
        </span>
      </div>
      {(d.when || where) && <p className="intel-micro daily-dev-meta">{[d.when, where].filter(Boolean).join(" · ")}</p>}
      {d.detail && <p className="daily-detail">{d.detail}</p>}
      {d.statements.length > 0 && (
        <div className="daily-quotes">
          {d.statements.map((s, i) => (
            <Statement key={i} s={s} />
          ))}
        </div>
      )}
      {d.significance && (
        <p className="daily-signif">
          <span className="intel-micro">Why it matters</span> {d.significance}
        </p>
      )}
      {d.sources.length > 0 && (
        <p className="daily-sources">
          <span className="intel-micro">Sources</span>
          {d.sources.map((u, i) => (
            <SourceLink key={i} url={u} />
          ))}
        </p>
      )}
    </li>
  );
}

function Theater({ t, i, date, snap, legend }: { t: DailyTheater; i: number; date: string; snap: Snapshot | null; legend: boolean }) {
  const top = maxBand(t.pulses);
  const series = snap?.theaters.find((x) => x.id === t.theater_id)?.series ?? snap?.theaters.find((x) => x.name === t.name)?.series ?? [];
  // Developments the map marks, by 1-based number, so they can wear the same badge.
  const mapped = new Map<number, number>();
  if (t.map) {
    const base = mapIndexBase(t.map, t.developments.length);
    for (const p of t.map.points) if (p.n !== null && p.n - base >= 0 && p.n - base < t.developments.length) mapped.set(p.n - base, p.n - base + 1);
  }
  return (
    <section id={anchorId(t, i)} className={`intel-frame daily-theater intel-band-${top}`} aria-label={t.name}>
      <header className="intel-frame-band">
        <h3>{t.name}</h3>
        <span className="intel-frame-meta">
          <span className="daily-temp">
            <HeatBar heat={t.temperature.heat} />
            <CoverageTag coverage={t.temperature.coverage} />
            <CoverageSpark series={series} name={t.name} />
          </span>
          <EscalationChips direction={t.escalation.direction} pace={t.escalation.pace} labelled />
        </span>
      </header>
      <div className="intel-frame-body">
        {t.pulses.length > 0 && (
          <div className="daily-block-pulses">
            {legend && <SpectrumLegend />}
            <div className="intel-pulse-grid" aria-label="Pulses for this theater">
              {t.pulses.map((p) => (
                <PulseCard
                  key={p.id}
                  base={{ id: p.id, name: p.name, position: p.position, band: p.band, d24: p.change_24h, d7: p.change_7d }}
                  full={findPulse(snap, p.id, p.name)}
                  reportDate={date}
                />
              ))}
            </div>
          </div>
        )}

        {t.bottom_line && (
          <div className="intel-bottom daily-bottom">
            <span className="intel-micro">Bottom line</span>
            <p>{t.bottom_line}</p>
          </div>
        )}

        <TheaterMapSlot map={t.map} developments={t.developments} />

        <KeyFigureTiles figures={t.key_figures} />

        {t.since_yesterday.length > 0 && (
          <div className="daily-block">
            <h4 className="intel-sub">Since yesterday</h4>
            <ul className="daily-since">
              {t.since_yesterday.map((c, k) => {
                const ch = CHANGE[c.kind];
                return (
                  <li key={k}>
                    <span className={`intel-chip intel-band-${ch.cls}`}>
                      {ch.glyph} {ch.label}
                    </span>
                    <span>{c.what}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {t.developments.length > 0 && (
          <div className="daily-block">
            <h4 className="intel-sub">Developments</h4>
            <DevTimeline developments={t.developments} reportDate={date} />
            <ol className="daily-devs">
              {t.developments.map((d, k) => (
                <Development key={k} d={d} n={mapped.get(k) ?? null} />
              ))}
            </ol>
          </div>
        )}

        {t.context.length > 0 && (
          <div className="daily-block">
            <h4 className="intel-sub">Context</h4>
            <ul className="daily-context">
              {t.context.map((c, k) => (
                <li key={k}>
                  <span className="intel-tl-date intel-tab">{c.when || "Earlier"}</span>
                  <div>
                    <p>{c.what}</p>
                    {c.why_relevant && <p className="intel-muted">{c.why_relevant}</p>}
                    {c.source && (
                      <p>
                        <SourceLink url={c.source} />
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {(t.outlook || t.watch_next.length > 0) && (
          <div className="daily-block daily-outlook">
            {t.outlook && (
              <div>
                <h4 className="intel-sub">Outlook</h4>
                <p className="intel-text">{t.outlook}</p>
              </div>
            )}
            {t.watch_next.length > 0 && (
              <div>
                <h4 className="intel-sub">Watch next</h4>
                <ul className="intel-unknowns">
                  {t.watch_next.map((w, k) => (
                    <li key={k}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {t.brief_slug && (
          <p className="daily-deep">
            <Link href={`/intel/briefs/${t.brief_slug}`}>Deep brief →</Link>
          </p>
        )}
      </div>
    </section>
  );
}

export default function DailyReport({ report, title }: { report: Daily; title: string }) {
  const snap = latestSnapshot();
  const firstWithPulses = report.theaters.findIndex((t) => t.pulses.length > 0);
  return (
    <>
      <div className="intel-strip" role="group" aria-label="Report status">
        <span className="intel-strip-title">{title} · Daily</span>
        <span className="intel-strip-item">{fmtDay(report.date)}</span>
        <span className="intel-strip-item">
          <span className="intel-micro">Built</span> {report.built_at ? fmtUtc(report.built_at) : "—"}
        </span>
        <span className="intel-strip-item">
          <b className="intel-num-sm">{report.theaters.length}</b> <span className="intel-micro">Theaters</span>
        </span>
        <span className="intel-trust" title={report.researched ? "Developments were checked against sources" : "Built from headlines; not independently checked"}>
          {report.researched ? "Researched" : "From headlines"}
        </span>
      </div>

      {(report.headline || report.the_day.length > 0) && (
        <section className="daily-lede" aria-label="The day">
          {report.headline && <h2 className="daily-headline">{report.headline}</h2>}
          {report.the_day.length > 0 && (
            <>
              <h3 className="intel-sub">The day</h3>
              <ul className="daily-day">
                {report.the_day.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}

      {report.theaters.length > 1 && (
        <nav className="daily-index" aria-label="Theaters in this report">
          {report.theaters.map((t, i) => (
            <a key={i} href={`#${anchorId(t, i)}`} className={`intel-chip intel-band-${maxBand(t.pulses)}`} title="Colour is the most severe Pulse reading in this theater">
              {t.name}
            </a>
          ))}
        </nav>
      )}

      {report.theaters.length === 0 ? (
        <p className="intel-empty">No theaters were covered in this report.</p>
      ) : (
        <div className="intel-frames">
          {report.theaters.map((t, i) => (
            <Theater key={i} t={t} i={i} date={report.date} snap={snap} legend={i === firstWithPulses} />
          ))}
        </div>
      )}

      {report.cross_theater.length > 0 && (
        <section className="intel-section" aria-labelledby="daily-across">
          <div className="intel-section-head">
            <h2 id="daily-across">Across theaters</h2>
            <span className="intel-micro">Where the stories connect</span>
          </div>
          <ul className="daily-across">
            {report.cross_theater.map((c, i) => (
              <li key={i}>
                {c.theaters.length > 0 && (
                  <span className="intel-chips">
                    {c.theaters.map((n, k) => (
                      <span key={k} className="intel-chip intel-band-unassessed">
                        {n}
                      </span>
                    ))}
                  </span>
                )}
                <p>{c.link}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
