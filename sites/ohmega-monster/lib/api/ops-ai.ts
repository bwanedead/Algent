import { aiBenchmarks, type Bench } from "@/lib/ai-benchmarks";

import { abs, badRequest, notFound, type ApiResult, type Args } from "./util";

// Op over the AI benchmark tracker (backend `ai_benchmarks/`): frontier model scores on public benchmarks, the frontier over time, open-weights against
// closed, per-lab series and saturation. Measured scores come from independent leaderboards (Epoch AI, SWE-bench, LMArena); `claimed` rows are the
// labs' own announcements, extracted automatically, and are NEVER part of a frontier or comparison.

const summary = (b: Bench) => ({
  id: b.id, name: b.name, source: b.source, unit: b.unit, ceiling: b.ceiling, models: b.n_models, as_of: b.as_of, best: b.best, saturation: b.saturation,
  change_12m: b.velocity, open_lag_days: b.open_lag_days, gap_closed_minus_open: b.gap, new_records: b.new_records, claimed: b.claimed.length,
});

export async function aiBenchmarksOp(a: Args): Promise<ApiResult> {
  const doc = await aiBenchmarks();
  if (!doc) throw notFound("AI benchmarks");
  const q = (a.benchmark ?? "").trim().toLowerCase();
  const lab = (a.lab ?? "").trim().toLowerCase();
  if (q.length > 80 || lab.length > 40) throw badRequest("benchmark or lab is too long");
  const rows = doc.benchmarks.filter((b) => !q || b.id === q || b.name.toLowerCase().includes(q));
  if (q && rows.length === 0) throw notFound(`benchmark "${q}"`);
  // A named benchmark returns its full series; the unfiltered call returns one summary row each (the series are large).
  const benchmarks = q ? rows.map((b) => ({ ...b, labs: lab ? Object.fromEntries(Object.entries(b.labs).filter(([k]) => k === lab)) : b.labs })) : rows.map(summary);
  return {
    data: { sources: doc.sources, labs: doc.labs.slice(0, 25), benchmarks },
    as_of: doc.as_of || null,
    cite_as: abs("/intel/ai"),
    source: "ohmega.ai-benchmarks/1",
    verification: "measured",
    note:
      "Scores are as published by each source (Epoch AI, CC BY 4.0; SWE-bench; LMArena) and are independently measured. Frontier = best measured score so far, placed by model release " +
      "date (Elo ratings: by leaderboard publish date, captured since our first fetch). Fractions are 0..1. `claimed` rows are lab-claimed scores from blogs and model cards: unverified, " +
      "attribute them to the lab. Check `sources[].stale` before relying on freshness; each benchmark's `as_of` is its newest result.",
  };
}
