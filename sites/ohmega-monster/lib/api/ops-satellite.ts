import { dataUrl, DATA_BASE } from "@/lib/data-base";
import { bySignal, satelliteDoc, type SatSite } from "@/lib/satellite";

import { abs, enumParam, limitParam, paginate, type ApiResult, type Args } from "./util";

// Op over the satellite watch (backend `satellite/`): watched places with their before / after Sentinel-2 chips, the change signal and night lights.
// Every number is Ohmega's own computation (`basis: our_computation`) and carries `method_note`, `baseline_since` and `n_obs`.

const LABELS = ["changed", "steady", "learning", "inconclusive"] as const;

export async function satelliteOp(a: Args): Promise<ApiResult> {
  const label = enumParam("label", a.label, LABELS);
  const country = (a.country ?? "").trim().toUpperCase();
  const kind = enumParam("kind", a.kind, ["asset", "zone"] as const);
  const doc = await satelliteDoc();
  const rows: SatSite[] = (doc?.sites ?? [])
    .filter((s) => s.latest && (!label || s.change?.label === label) && (!kind || s.kind === kind) && (!country || s.links.country === country))
    .sort(bySignal);
  const p = paginate(rows, limitParam(a.limit), a.cursor);
  return {
    data: { sites: p.items.map(withUrls), total: p.total, counts: doc?.counts ?? null, credit: doc?.credit ?? null, read_as: doc?.read_as ?? null },
    as_of: doc?.as_of ?? null,
    cite_as: abs("/intel/satellite"),
    source: "ohmega.satellite/1",
    verification: "ohmega_derived",
    next_cursor: p.next_cursor,
    note:
      "Ohmega's own computation from public imagery (Copernicus Sentinel-2 via Microsoft Planetary Computer; NASA VIIRS night lights via GIBS), not something a source reported. " +
      "A change score is a machine signal that two pictures of the same ground differ: it never says what changed or why, and cloud is not change (a mostly cloudy pair is 'inconclusive'). " +
      "'changed' means the score is far outside that site's own earlier scores; with fewer than 5 earlier looks the label is 'learning' and nothing is flagged. " +
      "Each judgement carries basis, method_note, baseline_since (when our history for the site starts) and n_obs (earlier looks it rests on). Chip URLs are 256 px PNGs of the same bbox.",
  };
}

function withUrls(s: SatSite) {

  const url = (key: string | undefined) => (key && DATA_BASE ? dataUrl(key) : null);
  return {
    ...s,
    baseline: s.baseline ? { ...s.baseline, chip_url: url(s.baseline.chip) } : null,
    latest: s.latest ? { ...s.latest, chip_url: url(s.latest.chip) } : null,
    cite_as: abs(s.links.asset ? `/intel/places/${s.links.asset}` : "/intel/satellite"),
  };
}
