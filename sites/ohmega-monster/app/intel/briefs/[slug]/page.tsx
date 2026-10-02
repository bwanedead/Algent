import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import Popover from "@/components/Popover";
import PulseTile from "@/components/PulseTile";
import { SpectrumLegend } from "@/components/PulseSpectrum";
import { ActorMap, EscalationChips, ProbBar, RELATION_KINDS } from "@/components/IntelViz";
import { allBriefSlugs, brief as loadBrief, type ChangeKind, type Effect, findPulse, latestSnapshot, type Plausibility, safeUrl, type Snapshot } from "@/lib/intel";
import { toWallPulse, type WallPulse } from "@/lib/pulse-wall";

type Params = { slug: string };

export const dynamicParams = false;

export function generateStaticParams(): Params[] {
  return allBriefSlugs().map((slug) => ({ slug }));
}

export function generateMetadata({ params }: { params: Params }): Metadata {
  const b = loadBrief(params.slug);
  if (!b) return { title: "Brief" };
  return { title: b.title, description: b.bottom_line.slice(0, 200) || undefined };
}

const LIKELIHOOD_CLASS: Record<string, string> = {
  "almost certain": "critical",
  likely: "severe",
  "roughly even": "elevated",
  unlikely: "calm",
  remote: "unassessed",
};
const INDICATOR_CLASS: Record<string, string> = { observed: "severe", emerging: "elevated", "not seen": "unassessed" };

const CHANGE: Record<ChangeKind, { glyph: string; cls: string; label: string }> = {
  escalated: { glyph: "▲", cls: "severe", label: "Escalated" },
  eased: { glyph: "▼", cls: "calm", label: "Eased" },
  new: { glyph: "●", cls: "elevated", label: "New" },
  resolved: { glyph: "✓", cls: "calm", label: "Resolved" },
  unchanged: { glyph: "=", cls: "unassessed", label: "Unchanged" },
};
const PLAUSIBILITY: Record<Plausibility, { cls: string; label: string }> = {
  leading: { cls: "severe", label: "Leading" },
  plausible: { cls: "elevated", label: "Plausible" },
  unlikely: { cls: "unassessed", label: "Unlikely" },
};

/** A snapshot Pulse (by exact name) as a tile-ready WallPulse plus its 7-day change; null when absent. */
function tileFor(snap: Snapshot | null, name: string): { pulse: WallPulse; d7: number | null } | null {
  const p = findPulse(snap, "", name);
  if (!p) return null;
  const sit = snap?.situations.find((x) => x.pulses.includes(p));
  return { pulse: toWallPulse(p, sit?.title ?? ""), d7: p.velocity_7d };
}

function Effects({ title, items }: { title: string; items: Effect[] }) {
  if (items.length === 0) return null;
  return (
    <section className="intel-section" aria-label={title}>
      <div className="intel-section-head">
        <h2>{title}</h2>
      </div>
      <ul className="intel-effects">
        {items.map((e, i) => (
          <li key={i}>
            {e.likelihood && <span className={`intel-chip intel-band-${LIKELIHOOD_CLASS[e.likelihood] ?? "unassessed"}`}>{e.likelihood}</span>}
            <div>
              <p>{e.effect}</p>
              {e.watch_for && (
                <p className="intel-muted">
                  <span className="intel-micro">Watch for</span> {e.watch_for}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function BriefPage({ params }: { params: Params }) {
  const b = loadBrief(params.slug);
  if (!b) notFound();
  const sorted = [...b.timeline].sort((x, y) => x.date.localeCompare(y.date));
  const snap = latestSnapshot();
  const hasPrevious = b.changes.length > 0;

  return (
    <article className="intel-page intel-brief">
      <Link href="/intel" className="intel-back">
        ← Intelligence
      </Link>
      <header className="intel-brief-head">
        <p className="intel-micro">
          Brief{b.theater_name ? ` · ${b.theater_name}` : ""}
          {b.as_of ? ` · as of ${b.as_of.slice(0, 10)}` : ""}
          {b.researched ? " · researched" : " · from reports only"}
        </p>
        <h1>{b.title}</h1>
        {b.focus && (
          <p className="intel-muted">
            <span className="intel-micro">Focus</span> {b.focus}
          </p>
        )}
      </header>

      {b.bottom_line && (
        <aside className="intel-bottom" aria-label="Bottom line">
          <span className="intel-micro">Bottom line</span>
          <p>{b.bottom_line}</p>
        </aside>
      )}

      {b.changes.length > 0 && (
        <section className="intel-section" aria-label="Since our last brief">
          <div className="intel-section-head">
            <h2>Since our last brief</h2>
          </div>
          <ul className="intel-changes">
            {b.changes.map((c, i) => {
              const k = CHANGE[c.kind];
              return (
                <li key={i}>
                  <span className={`intel-chip intel-band-${k.cls}`} title={k.label}>
                    <span aria-hidden="true">{k.glyph}</span> {k.label}
                  </span>
                  <div>
                    <p>{c.what}</p>
                    {c.basis && <p className="intel-muted">{c.basis}</p>}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {b.judgments.length > 0 && (
        <section className="intel-section" aria-label="Key judgments">
          <div className="intel-section-head">
            <h2>Key judgments</h2>
            <span className="intel-micro">Forecasts are scored publicly when they resolve.</span>
          </div>
          <ul className="intel-judgments">
            {b.judgments.map((j, i) => (
              <li key={i}>
                <div className="intel-j-prob">
                  <span className="intel-num intel-j-num">{j.probability}%</span>
                  <ProbBar value={j.probability} />
                </div>
                <div className="intel-j-body">
                  <p className="intel-strong">{j.statement}</p>
                  {j.horizon && <p className="intel-micro">By {j.horizon}</p>}
                  {(j.basis || j.resolves_yes_if || j.resolves_no_if) && (
                    <Popover label={`Basis and resolution: ${j.statement}`} trigger="Basis and how it resolves" triggerClassName="pop-link">
                      {j.basis && <p className="intel-muted">{j.basis}</p>}
                      {j.resolves_yes_if && (
                        <p>
                          <span className="intel-micro">Yes if</span> {j.resolves_yes_if}
                        </p>
                      )}
                      {j.resolves_no_if && (
                        <p>
                          <span className="intel-micro">No if</span> {j.resolves_no_if}
                        </p>
                      )}
                    </Popover>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="intel-section" aria-label="Escalation">
        <div className="intel-section-head">
          <h2>Escalation</h2>
          <EscalationChips direction={b.escalation.direction} pace={b.escalation.pace} />
        </div>
        {b.escalation.assessment ? <p className="intel-text">{b.escalation.assessment}</p> : <p className="intel-empty">No assessment given.</p>}
      </section>

      {b.situation && (
        <section className="intel-section" aria-label="Where things stand">
          <div className="intel-section-head">
            <h2>Where things stand</h2>
          </div>
          {b.situation.split(/\n{2,}/).map((para, i) => (
            <p key={i} className="intel-text">
              {para}
            </p>
          ))}
        </section>
      )}

      {sorted.length > 0 && (
        <section className="intel-section" aria-label="Timeline">
          <div className="intel-section-head">
            <h2>Timeline</h2>
          </div>
          <ol className="intel-timeline">
            {sorted.map((t, i) => {
              const href = safeUrl(t.source);
              return (
                <li key={i}>
                  <time className="intel-tl-date intel-tab">{t.date}</time>
                  <div>
                    <p>{t.what}</p>
                    <p className="intel-tl-meta">
                      <span className={`intel-chip ${t.verification === "researched" ? "intel-band-calm" : "intel-band-unassessed"}`}>
                        {t.verification === "researched" ? "Researched" : "Reported — unverified"}
                      </span>
                      {t.actors.length > 0 && <span className="intel-micro">{t.actors.join(" · ")}</span>}
                      {href && (
                        <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="intel-micro">
                          Source ↗
                        </a>
                      )}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      )}

      {b.relations.length > 0 && (
        <section className="intel-section" aria-label="Actor map">
          <div className="intel-section-head">
            <h2>Actor map</h2>
            <span className="intel-micro">Who is acting on whom</span>
          </div>
          <ActorMap relations={b.relations} />
          <div className="intel-table-wrap">
            <table className="intel-table">
              <caption className="intel-sr">Relations between actors</caption>
              <thead>
                <tr>
                  <th scope="col">From</th>
                  <th scope="col">Action</th>
                  <th scope="col">To</th>
                  <th scope="col">Note</th>
                  <th scope="col">Date</th>
                </tr>
              </thead>
              <tbody>
                {b.relations.map((r, i) => (
                  <tr key={i}>
                    <td>{r.source}</td>
                    <td>
                      <span className={`intel-kind intel-k-${r.kind in RELATION_KINDS ? r.kind : "other"}`}>{RELATION_KINDS[r.kind] ?? r.kind}</span>
                    </td>
                    <td>{r.target}</td>
                    <td className="intel-muted">{r.note}</td>
                    <td className="intel-tab">{r.date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {b.indicators.length > 0 && (
        <section className="intel-section" aria-label="Indicators and warnings">
          <div className="intel-section-head">
            <h2>Indicators &amp; warnings</h2>
          </div>
          <div className="intel-table-wrap">
            <table className="intel-table">
              <thead>
                <tr>
                  <th scope="col">Signal</th>
                  <th scope="col">Status</th>
                  <th scope="col">What it would mean</th>
                </tr>
              </thead>
              <tbody>
                {b.indicators.map((x, i) => (
                  <tr key={i}>
                    <td>{x.signal}</td>
                    <td>
                      {x.previous_status && x.previous_status !== x.status ? (
                        <span className="intel-move">
                          <span className="intel-micro">{x.previous_status}</span>
                          <span aria-label="to"> → </span>
                          <span className={`intel-chip intel-band-${INDICATOR_CLASS[x.status] ?? "unassessed"}`}>{x.status}</span>
                        </span>
                      ) : (
                        <span className={`intel-chip intel-band-${INDICATOR_CLASS[x.status] ?? "unassessed"}`}>{x.status}</span>
                      )}
                      {!x.previous_status && hasPrevious && <span className="intel-chip intel-band-elevated intel-new-chip">new</span>}
                    </td>
                    <td className="intel-muted">{x.meaning}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {b.alternatives.length > 0 && (
        <section className="intel-section" aria-label="Competing explanations">
          <div className="intel-section-head">
            <h2>Competing explanations</h2>
            <span className="intel-micro">Most to least plausible</span>
          </div>
          <ul className="intel-alts">
            {b.alternatives.map((a, i) => {
              const p = PLAUSIBILITY[a.plausibility];
              return (
                <li key={i}>
                  <div className="intel-alt-head">
                    <span className={`intel-chip intel-band-${p.cls}`}>{p.label}</span>
                    <strong className="intel-strong">{a.hypothesis}</strong>
                  </div>
                  {(a.consistent_with || a.inconsistent_with) && (
                    <dl className="intel-ends">
                      {a.consistent_with && (
                        <div>
                          <dt>For</dt>
                          <dd>{a.consistent_with}</dd>
                        </div>
                      )}
                      {a.inconsistent_with && (
                        <div>
                          <dt>Against</dt>
                          <dd>{a.inconsistent_with}</dd>
                        </div>
                      )}
                    </dl>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <Effects title="Second-order effects" items={b.second_order} />
      <Effects title="Peripheral effects" items={b.peripheral} />

      {b.unknowns.length > 0 && (
        <section className="intel-section" aria-label="Unknowns">
          <div className="intel-section-head">
            <h2>What we do not know</h2>
          </div>
          <ul className="intel-unknowns">
            {b.unknowns.map((u, i) => (
              <li key={i}>{u}</li>
            ))}
          </ul>
        </section>
      )}

      {b.would_change_our_mind.length > 0 && (
        <section className="intel-section" aria-label="What would change our mind">
          <div className="intel-section-head">
            <h2>What would change our mind</h2>
          </div>
          <ul className="intel-unknowns">
            {b.would_change_our_mind.map((u, i) => (
              <li key={i}>{u}</li>
            ))}
          </ul>
        </section>
      )}

      {b.pulses.length > 0 && (
        <section className="intel-section" aria-label="Related Pulses">
          <div className="intel-section-head">
            <h2>Related Pulses</h2>
          </div>
          <SpectrumLegend />
          <div className="pt-grid">
            {b.pulses.map((name) => {
              const t = tileFor(snap, name);
              return t ? (
                <PulseTile key={t.pulse.id} pulse={t.pulse} delta={t.d7 ?? undefined} period="7d" />
              ) : (
                <span key={name} className="intel-chip intel-band-unassessed" title="Not in the current Pulse snapshot">
                  {name}
                </span>
              );
            })}
          </div>
        </section>
      )}
    </article>
  );
}
