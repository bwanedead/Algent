import PageTag from "@/components/PageTag";
import type { Metadata } from "next";
import Link from "next/link";

import { LabRaceChart, OpenClosedChart } from "@/components/ai/AiCharts";
import BenchCard from "@/components/ai/BenchCard";
import ScoresTable, { type ScoreRow } from "@/components/ai/ScoresTable";
import { ago, aiBenchmarks, fmtDate, fmtDelta, fmtScore, type Bench } from "@/lib/ai-benchmarks";
import { labColor } from "@/lib/ai-labs";

import "@/app/daily/daily.css";
import "@/app/situations/situations.css";
import "@/components/ai/ai.css";

export const metadata: Metadata = {
  title: "AI benchmarks",
  description: "How fast frontier AI is moving: the best score on every public benchmark over time, open-weights models against closed ones, each lab's race, and how close each benchmark is to saturation.",
  alternates: { canonical: "/intel/ai", types: { "application/json": "/api/v1/ai-benchmarks" } },
};

// The AI desk's numbers (backend `ai_benchmarks/`, docs/architecture/ai-desk.md): scores collected twice a day from free public leaderboards, a frontier
// derived per benchmark, and a capped daily pass that records what labs CLAIM before any leaderboard carries it. Claims are always drawn apart from measured
// scores (hollow diamonds) and never enter a line.
export const revalidate = 3600; // lib/store.ts TTL.static: slow products (markets every 4 h, benchmarks every 12 h)

const CARDS_SHOWN = 24;
const PAIRS_SHOWN = 6;
const FEATURED = "epoch-eci";

const sumRows = (bs: Bench[], f: (b: Bench) => number): number => bs.reduce((n, b) => n + f(b), 0);

export default async function AiBenchmarksPage() {
  const doc = await aiBenchmarks();
  if (!doc) {
    return (
      <div className="intel-page th-page">
        <p className="th-kicker"><PageTag kind="data" detail="AI benchmarks" /></p>
        <h1 className="th-claim">AI benchmarks</h1>
        <p className="th-asof">No benchmark scores have been published yet. The collector has to run once first.</p>
      </div>
    );
  }
  const names = Object.fromEntries(doc.labs.map((l) => [l.id, l.name]));
  const staleSource = new Set(doc.sources.filter((s) => s.stale).map((s) => s.source));
  const featured = doc.benchmarks.find((b) => b.id === FEATURED && Object.keys(b.labs).length > 0) ?? doc.benchmarks.find((b) => Object.keys(b.labs).length > 0);
  const charted = doc.benchmarks.filter((b) => b.frontier.length > 0 && b.id !== featured?.id);
  const pairs = doc.benchmarks.filter((b) => b.open.length > 0 && b.closed.length > 0).slice(0, PAIRS_SHOWN);
  const claims = doc.benchmarks.flatMap((b) => b.claimed.map((c) => ({ b, c }))).sort((x, y) => y.c.d.localeCompare(x.c.d)).slice(0, 30);
  const now = new Date();
  const rows: ScoreRow[] = doc.benchmarks
    .filter((b) => b.best)
    .map((b) => {
      const best = b.best as NonNullable<Bench["best"]>;
      return {
        id: b.id, name: b.name, url: b.source_url, best: fmtScore(b.unit, best.s), model: best.m, lab: best.l, labName: names[best.l] ?? best.l, labColor: labColor(best.l),
        weights: best.weights === "unknown" ? "" : best.weights, models: b.n_models, saturation: b.saturation,
        year: b.velocity === null ? "n/a" : fmtDelta(b.unit, b.velocity), yearSort: b.velocity, asOf: b.as_of, asOfLabel: b.as_of ? fmtDate(b.as_of) : "n/a",
        stale: staleSource.has(b.source),
      };
    });

  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <PageTag kind="data" detail="AI benchmarks" /> <Link href="/daily/ai" className="xt">AI daily →</Link> <Link href="/explore" className="xt">explore →</Link>
      </p>
      <h1 className="th-claim">AI benchmarks</h1>
      <p className="th-asof">
        {doc.benchmarks.length} benchmarks · {sumRows(doc.benchmarks, (b) => b.n_results).toLocaleString("en-US")} measured scores · {doc.labs.length} labs
        {claims.length > 0 ? ` · ${claims.length} lab claims, not independently measured` : ""}. Updated {ago(doc.as_of, now)}.
      </p>

      <ul className="ai-fresh" aria-label="Freshness of each source">
        {doc.sources.map((s) => (
          <li key={s.source} className={s.stale ? "is-stale" : undefined}>
            <b>
              {s.page ? <a href={s.page} rel="noopener noreferrer" className="xt">{s.name}</a> : s.name}
              {s.stale && <span className="ai-tag">stale</span>}
            </b>
            fetched {ago(s.last_ok, now)}
            {s.newest_result ? ` · newest result ${fmtDate(s.newest_result)}` : ""}
            {s.stale && s.reasons.length > 0 && <><br />{s.reasons.join("; ")}</>}
          </li>
        ))}
      </ul>

      {featured && (
        <>
          <h2 className="ai-h2">The race: {featured.name}</h2>
          <p className="ai-note">
            Each line is one lab&apos;s best score so far, labelled at its end. {featured.best ? `The frontier is ${fmtScore(featured.unit, featured.best.s)} (${featured.best.m}, ${fmtDate(featured.best.d)}).` : ""}
          </p>
          <div className="ai-hero">
            <LabRaceChart bench={featured} names={names} />
          </div>
        </>
      )}

      {pairs.length > 0 && (
        <>
          <h2 className="ai-h2">Open weights against closed</h2>
          <p className="ai-note">
            The best open-weights model against the best closed one on the same benchmark. The time gap is how long ago the closed frontier first reached today&apos;s open-weights best.
          </p>
          <div className="ai-pairs">
            {pairs.map((b) => (
              <article key={b.id} className="ai-card">
                <header className="ai-card-h">
                  <h3 className="ai-card-t">{b.name}</h3>
                  <span className={`ai-asof${staleSource.has(b.source) ? " is-stale" : ""}`}>{b.as_of ? `as of ${fmtDate(b.as_of)}` : ""}</span>
                </header>
                <OpenClosedChart bench={b} />
                <p className="ai-pair-lag">
                  {b.gap !== null && b.gap > 0 ? `Open trails by ${fmtDelta(b.unit, b.gap).replace("+", "")}` : "Open weights lead or tie"}
                  {b.open_lag_days !== null && b.open_lag_days > 30 ? `, about ${Math.round(b.open_lag_days / 30)} months behind in time` : ""}
                </p>
              </article>
            ))}
          </div>
        </>
      )}

      <h2 className="ai-h2">Every benchmark: the best score over time</h2>
      <p className="ai-note">
        The line steps up each time a model beats every earlier one; each dot is coloured by the lab that set the record. Hollow diamonds are scores a lab claims that no leaderboard has measured.
      </p>
      <div className="ai-grid-cards">
        {charted.slice(0, CARDS_SHOWN).map((b) => <BenchCard key={b.id} bench={b} sourceStale={staleSource.has(b.source)} />)}
      </div>
      {charted.length > CARDS_SHOWN && (
        <details className="ai-more">
          <summary>{charted.length - CARDS_SHOWN} more benchmarks</summary>
          <div className="ai-grid-cards">
            {charted.slice(CARDS_SHOWN).map((b) => <BenchCard key={b.id} bench={b} sourceStale={staleSource.has(b.source)} />)}
          </div>
        </details>
      )}

      <h2 className="ai-h2">Latest scores</h2>
      <p className="ai-note">One row per benchmark: its current leader. Click a heading to sort. &quot;Of ceiling&quot; is the leader&apos;s score as a share of the best achievable score.</p>
      <ScoresTable rows={rows} />

      {claims.length > 0 && (
        <>
          <h2 className="ai-h2">Claimed by the labs, not independently measured</h2>
          <p className="ai-note">
            Scores found in a lab&apos;s own announcement or model card, extracted automatically once a day. They appear days before any leaderboard runs the model and are the lab&apos;s
            word, so they are kept out of every line above.
          </p>
          <ul className="ai-claims">
            {claims.map(({ b, c }) => (
              <li key={`${b.id}-${c.m}-${c.d}`}>
                <span className="ai-diamond" aria-hidden="true">◇</span>
                <b>{c.m}</b> {fmtScore(b.unit, c.s)} on {b.name}, {c.lab_name || names[c.l] || "lab"} ({fmtDate(c.d)}){" "}
                {c.url && <a href={c.url} rel="noopener noreferrer" className="xt">source</a>}
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="th-asof">
        Sources: {doc.sources.filter((s) => s.source !== "self_reported").map((s) => `${s.name} (${s.licence})`).join("; ")}. A score is placed by the model&apos;s release
        date (or the leaderboard&apos;s publish date for Elo ratings, which we have captured since our first fetch). Machine access:{" "}
        <Link href="/api/v1/ai-benchmarks" className="xt">/api/v1/ai-benchmarks</Link>.
      </p>
    </div>
  );
}
