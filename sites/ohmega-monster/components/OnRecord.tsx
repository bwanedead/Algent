import IsoFlags from "./IsoFlags";
import Popover from "./Popover";
import { dayLabel, isQuote, officeOf, signalLabel, stanceLabel, type OnRecord } from "@/lib/record-model";

import "./record.css";

export const SAID_NOTE = "A statement shows what was said, not that it is true.";
const TOP = 3;

/** One statement: flag, speaker and office, date, the exact words (quoted) or a marked paraphrase, signal, link. */
export function RecordRow({ r }: { r: OnRecord }) {
  const toward = r.about.slice(0, 3).join(", ");
  return (
    <li className="rec-row">
      <p className="rec-who">
        <IsoFlags codes={r.iso2 ? [r.iso2] : []} />
        <b>{r.speaker}</b>
        <span className="rec-muted">
          {officeOf(r) ? ` · ${officeOf(r)}` : ""} · {dayLabel(r.date)}
        </span>
      </p>
      <p className="rec-said">
        {isQuote(r) ? (
          <>&ldquo;{r.quote}&rdquo;</>
        ) : (
          <>
            <span className="rec-tag">paraphrase</span> {r.paraphrase}
          </>
        )}
      </p>
      <p className="rec-meta">
        <span className="rec-sig">{signalLabel(r.signal)}</span>
        {toward && (
          <span className="rec-muted">
            {" "}
            · {r.stance === 0 ? "about" : `${stanceLabel(r.stance)} toward`} {toward}
          </span>
        )}
        {r.url && (
          <>
            {" "}
            <a href={r.url} target="_blank" rel="noopener noreferrer">
              transcript ↗
            </a>
          </>
        )}
      </p>
    </li>
  );
}

/** A section's or brief's record: top three visible, the rest on demand. `note` prints the said-not-true line. */
export default function OnRecordBlock({ rows, title, note = false }: { rows: OnRecord[]; title: string; note?: boolean }) {
  if (rows.length === 0) return null;
  const rest = rows.slice(TOP);
  return (
    <section className="rec" aria-label={`On the record: ${title}`}>
      <h3 className="geo-h2">On the record</h3>
      <ul className="rec-list">
        {rows.slice(0, TOP).map((r) => (
          <RecordRow key={r.id} r={r} />
        ))}
      </ul>
      {rest.length > 0 && (
        <Popover label={`On the record: ${title}`} triggerClassName="geo-link-btn" trigger={<>{rest.length} more on the record ›</>}>
          <div className="geo-pd">
            <p className="geo-pd-title">{title}</p>
            <ul className="rec-list">
              {rest.map((r) => (
                <RecordRow key={r.id} r={r} />
              ))}
            </ul>
            <p className="rec-note">{SAID_NOTE}</p>
          </div>
        </Popover>
      )}
      {note && <p className="rec-note">{SAID_NOTE}</p>}
    </section>
  );
}
