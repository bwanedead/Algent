import { SourceLink } from "@/components/DailyVisuals";
import { shortDay } from "@/lib/daily";
import type { DailyAssetEvent } from "@/lib/daily";
import { statusTone, STATUS_LABEL, STATUS_MEANING, TYPE_LABEL, type GeoLogRow } from "@/lib/geoledger-shared";

// "Strike & status log" under a theater: the named facilities, vessels and entities the reports say something dated about, newest
// first, each line saying WHO says it (a claim is a party's word, not a confirmation: the wording and colour of `status` keep them
// apart). The rows are the geoledger's week of events at the places on the theater's map (lib/geoledger.ts) or, without a database,
// what the day's extraction put on the section. Presentational only: no data access here.

export type LogLine = {
  key: string;
  date: string;
  name: string;
  type: GeoLogRow["type"];
  status: GeoLogRow["status"];
  claimant: string;
  confidence: GeoLogRow["confidence"];
  sources: string[];
  note: string;
};

/** The log's lines: the ledger's rows when it has any for this theater, else the section's own extraction. */
export function logLines(week: GeoLogRow[], own: DailyAssetEvent[]): LogLine[] {
  const rows: LogLine[] =
    week.length > 0
      ? week.map((e) => ({ key: e.id, date: e.occurred_on, name: e.name, type: e.type, status: e.status, claimant: e.claimant, confidence: e.confidence, sources: e.sources, note: e.note }))
      : own.map((e, i) => ({ key: `${e.asset_id}-${i}`, date: e.date, name: e.name, type: e.type, status: e.status, claimant: e.claimant, confidence: e.confidence, sources: e.sources, note: e.note }));
  return rows.sort((a, b) => b.date.localeCompare(a.date) || a.name.localeCompare(b.name));
}

export default function AssetStatusLog({ lines }: { lines: LogLine[] }) {
  return (
    <>
      <p className="geo-gloss">
        Named places and things the reports say something dated about. Each line gives who says it: &ldquo;claimed struck&rdquo; is a party&apos;s own word, and only a
        second source turns it into reported or confirmed damage.
      </p>
      <ul className="geo-ctx">
        {lines.map((l) => (
          <li key={l.key}>
            <span className="geo-micro geo-ctx-when">{shortDay(l.date)}</span>
            <span>
              <span className="geo-ctx-what">
                <span aria-hidden="true" style={{ color: statusTone(l.status) }}>● </span>
                {l.name}
              </span>{" "}
              <span className="geo-muted">
                ({TYPE_LABEL[l.type].toLowerCase()}) · <b className="geo-strong" title={STATUS_MEANING[l.status]}>{STATUS_LABEL[l.status]}</b> · said by {l.claimant}
                {l.confidence === "low" ? " · low confidence" : ""}
              </span>
              {l.sources.slice(0, 2).map((u) => (
                <span key={u}>
                  {" "}
                  <SourceLink url={u} />
                </span>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}
