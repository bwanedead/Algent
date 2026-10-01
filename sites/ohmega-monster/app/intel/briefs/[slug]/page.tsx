import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ActorMap, EscalationChips, RELATION_KINDS } from "@/components/IntelViz";
import { allBriefSlugs, brief as loadBrief, type Effect, safeUrl } from "@/lib/intel";

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
                      <span className={`intel-chip intel-band-${INDICATOR_CLASS[x.status] ?? "unassessed"}`}>{x.status}</span>
                    </td>
                    <td className="intel-muted">{x.meaning}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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

      {b.pulses.length > 0 && (
        <section className="intel-section" aria-label="Related Pulses">
          <div className="intel-section-head">
            <h2>Related Pulses</h2>
          </div>
          <p className="intel-chips">
            {b.pulses.map((p) => (
              <Link key={p} href="/intel#intel-pulses" className="intel-chip intel-band-unassessed">
                {p}
              </Link>
            ))}
          </p>
        </section>
      )}
    </article>
  );
}
