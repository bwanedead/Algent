import Link from "next/link";

import IsoFlags from "@/components/IsoFlags";
import Glyph from "@/components/vl/Glyph";
import { confidenceWord, kindOf, shortDate, untilWords, type ComingRow } from "@/lib/calendar-shared";

import "./calendar.css";

// "Coming up": a few dated things ahead as hairline-ruled rows (date and distance, kind glyph, title, flags). Used on Home under the
// glance band, in each theater's daily section (the rows the day's writer was shown, stored with the report) and on actor pages. Pure
// and server-safe. A date is a plan: items taken from our own earlier reports say so, and nothing here claims they will happen.

export default function ComingStrip({ rows, today, heading = "Coming up", limit = 5, all = true, dense = false }: { rows: ComingRow[]; today: string; heading?: string; limit?: number; all?: boolean; dense?: boolean }) {
  if (rows.length === 0) return null;
  const shown = rows.slice(0, limit);
  return (
    <aside className={`cal-strip${dense ? " is-dense" : ""}`} aria-label={heading}>
      <p className="cal-strip-head">
        <span>{heading}</span>
        {all && (
          <Link href="/calendar" className="xt">
            calendar →
          </Link>
        )}
      </p>
      <ul>
        {shown.map((r, i) => {
          const k = kindOf(r.kind);
          const when = r.end_date && r.end_date > r.date ? `${shortDate(r.date)} to ${shortDate(r.end_date)}` : shortDate(r.date);
          return (
            <li key={`${r.date}-${r.title}-${i}`} className="cal-row">
              <span className="cal-when" title={r.date}>
                <span className="cal-when-d">{when}</span>
                <span className="cal-when-n">{untilWords(r.date, today)}</span>
              </span>
              <span className={`cal-glyph cal-k-${r.kind}`} title={k.label}>
                <Glyph name={k.glyph} size={14} />
              </span>
              <span className="cal-title">
                {r.url && !r.ours ? (
                  <a href={r.url} className="cal-link" rel="noopener noreferrer" title={`${k.label}, ${confidenceWord(r.confidence, r.ours)}`}>
                    {r.title}
                  </a>
                ) : (
                  <span title={`${k.label}, ${confidenceWord(r.confidence, r.ours)}`}>{r.title}</span>
                )}
                {r.ours && <span className="cal-flag"> unconfirmed</span>}
              </span>
              <IsoFlags codes={r.countries.slice(0, 3)} />
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
