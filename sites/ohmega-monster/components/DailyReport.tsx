import Link from "next/link";

import type { Daily, DailyChangeKind, DailyDevelopment, DailyPulse, DailyStatement, DailyTheater } from "@/lib/daily";
import { fmtDay } from "@/lib/daily";
import { BAND_LABEL, fmtUtc, maxBand, safeUrl } from "@/lib/intel";

import { EscalationChips, HeatBar } from "./IntelViz";

const TREND = {
  heating: { glyph: "▲", cls: "severe", label: "Heating" },
  steady: { glyph: "◆", cls: "elevated", label: "Steady" },
  cooling: { glyph: "▼", cls: "calm", label: "Cooling" },
  new: { glyph: "●", cls: "unassessed", label: "New" },
} as const;

const CHANGE: Record<DailyChangeKind, { glyph: string; cls: string; label: string }> = {
  escalated: { glyph: "▲", cls: "severe", label: "Escalated" },
  eased: { glyph: "▼", cls: "calm", label: "Eased" },
  new: { glyph: "●", cls: "elevated", label: "New" },
  resolved: { glyph: "✓", cls: "calm", label: "Resolved" },
  unchanged: { glyph: "=", cls: "unassessed", label: "Unchanged" },
};

const anchorId = (t: DailyTheater, i: number) => `theater-${i}-${t.theater_id.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;

function fmtDelta(v: number | null): string {
  if (v === null) return "—";
  const r = Math.round(v * 10) / 10;
  if (r === 0) return "◆ 0";
  return `${r > 0 ? "▲ +" : "▼ −"}${Math.abs(r)}`;
}
const deltaClass = (v: number | null) => (v === null || Math.round(v * 10) === 0 ? "flat" : v > 0 ? "up" : "down");

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function SourceLink({ url, label }: { url: string; label?: string }) {
  const href = safeUrl(url);
  if (!href) return url ? <span className="intel-micro">{url}</span> : null;
  return (
    <a href={href} className="daily-src" target="_blank" rel="noopener noreferrer nofollow">
      {label ?? host(href)} ↗
    </a>
  );
}

/** Reserved slot for a future theater map. Renders nothing until the data carries one. */
export function TheaterMapSlot({ map }: { map: unknown | null }) {
  if (map === null || map === undefined) return null;
  return <div className="daily-map-slot" aria-hidden="true" />;
}

function PulseMini({ p }: { p: DailyPulse }) {
  return (
    <Link href={`/intel#pulse-${encodeURIComponent(p.id)}`} className={`daily-pulse intel-band-${p.band}`} title={`${p.name}: open on the Intelligence board`}>
      <span className="daily-pulse-name">{p.name}</span>
      <span className="daily-pulse-main">
        <span className={p.position === null ? "intel-num-sm intel-muted" : "intel-num-sm"}>{p.position === null ? "—" : Math.round(p.position)}</span>
        <span className={`intel-chip intel-band-${p.band}`}>{BAND_LABEL[p.band]}</span>
      </span>
      <span className="daily-pulse-deltas">
        <span className={`intel-delta intel-delta-${deltaClass(p.change_24h)}`}>
          {fmtDelta(p.change_24h)}
          <span className="intel-micro"> 24h</span>
        </span>
        <span className={`intel-delta intel-delta-${deltaClass(p.change_7d)}`}>
          {fmtDelta(p.change_7d)}
          <span className="intel-micro"> 7d</span>
        </span>
      </span>
    </Link>
  );
}

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

function Development({ d }: { d: DailyDevelopment }) {
  const verified = d.verification === "researched";
  return (
    <li className="daily-dev">
      <div className="daily-dev-head">
        <h4>{d.headline}</h4>
        <span className={`intel-chip intel-band-${verified ? "calm" : "elevated"}`} title={verified ? "Checked against sources we read" : "Reported by outlets; not independently checked"}>
          {verified ? "Researched" : "Reported — unverified"}
        </span>
      </div>
      {(d.when || d.where) && <p className="intel-micro daily-dev-meta">{[d.when, d.where].filter(Boolean).join(" · ")}</p>}
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

function Theater({ t, i }: { t: DailyTheater; i: number }) {
  const tr = TREND[t.temperature.trend];
  const top = maxBand(t.pulses);
  return (
    <section id={anchorId(t, i)} className={`intel-frame daily-theater intel-band-${top}`} aria-label={t.name}>
      <header className="intel-frame-band">
        <h3>{t.name}</h3>
        <span className="intel-frame-meta">
          <span className="daily-temp">
            <HeatBar heat={t.temperature.heat} />
            <span className={`intel-trend intel-band-${tr.cls}`}>
              {tr.glyph} {tr.label}
            </span>
          </span>
          <EscalationChips direction={t.escalation.direction} pace={t.escalation.pace} />
        </span>
      </header>
      <div className="intel-frame-body">
        {t.pulses.length > 0 && (
          <div className="daily-pulses" aria-label="Pulses for this theater">
            {t.pulses.map((p) => (
              <PulseMini key={p.id} p={p} />
            ))}
          </div>
        )}

        {t.bottom_line && (
          <div className="intel-bottom daily-bottom">
            <span className="intel-micro">Bottom line</span>
            <p>{t.bottom_line}</p>
          </div>
        )}

        <TheaterMapSlot map={t.map} />

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
            <ol className="daily-devs">
              {t.developments.map((d, k) => (
                <Development key={k} d={d} />
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
          {report.theaters.map((t, i) => {
            const tr = TREND[t.temperature.trend];
            return (
              <a key={i} href={`#${anchorId(t, i)}`} className={`intel-chip intel-band-${tr.cls}`}>
                {tr.glyph} {t.name}
              </a>
            );
          })}
        </nav>
      )}

      {report.theaters.length === 0 ? (
        <p className="intel-empty">No theaters were covered in this report.</p>
      ) : (
        <div className="intel-frames">
          {report.theaters.map((t, i) => (
            <Theater key={i} t={t} i={i} />
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
