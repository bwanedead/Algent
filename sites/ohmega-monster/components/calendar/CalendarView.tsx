"use client";

import { useMemo, useState } from "react";

import IsoFlags from "@/components/IsoFlags";
import Glyph from "@/components/vl/Glyph";
import {
  addDays, confidenceWord, countriesOf, density, kindOf, KINDS, shortDate, weekday, weeks, type CalendarKind, type CalendarRow,
} from "@/lib/calendar-shared";
import { countryName } from "@/lib/flags";

import "./calendar.css";

// The /calendar page's body: a density strip over the next 30 days, then the days grouped by week in a Monday-first grid (one cell per
// day, an item in every day it covers), with filters for kind and country. On a phone the grid becomes an agenda (only days with
// something). Receives plain rows and today's date from the server page; imports only the pure shared files (no server-only modules).

const SPAN = 30;

export default function CalendarView({ rows, today }: { rows: CalendarRow[]; today: string }) {
  const [kinds, setKinds] = useState<Set<CalendarKind>>(new Set());
  const [country, setCountry] = useState("");
  const inWindow = useMemo(() => rows.filter((r) => r.on_date <= addDays(today, SPAN)), [rows, today]);
  const present = useMemo(() => new Set(inWindow.map((r) => r.kind)), [inWindow]);
  const countries = useMemo(() => countriesOf(inWindow), [inWindow]);
  const shown = useMemo(
    () => inWindow.filter((r) => (kinds.size === 0 || kinds.has(r.kind)) && (!country || r.countries.includes(country))),
    [inWindow, kinds, country],
  );
  const grid = useMemo(() => weeks(shown, today, SPAN), [shown, today]);
  const bars = useMemo(() => density(shown, today, SPAN), [shown, today]);
  const peak = Math.max(1, ...bars);
  const toggle = (k: CalendarKind) => setKinds((prev) => {
    const next = new Set(prev);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    return next;
  });

  return (
    <div className="cal-view">
      <div className="cal-filters" role="group" aria-label="Filter the calendar">
        <ul className="cal-chips">
          {KINDS.filter((k) => present.has(k.id)).map((k) => (
            <li key={k.id}>
              <button type="button" className={`cal-chip cal-k-${k.id}${kinds.has(k.id) ? " is-on" : ""}`} aria-pressed={kinds.has(k.id)} onClick={() => toggle(k.id)}>
                <Glyph name={k.glyph} size={13} /> {k.label}
              </button>
            </li>
          ))}
        </ul>
        {countries.length > 0 && (
          <label className="cal-country">
            <span className="vl-label">Country</span>
            <select value={country} onChange={(e) => setCountry(e.target.value)}>
              <option value="">All</option>
              {countries.map((c) => (
                <option key={c} value={c}>
                  {countryName(c)}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="cal-density" role="img" aria-label={`Items per day over the next ${SPAN} days: ${shown.length} in total`}>
        {bars.map((n, i) => (
          <span key={i} className={`cal-bar${i === 0 ? " is-today" : ""}`} title={`${shortDate(addDays(today, i))}: ${n}`}>
            <span style={{ height: `${(n / peak) * 100}%` }} />
          </span>
        ))}
        <span className="cal-density-l">today</span>
        <span className="cal-density-r">{shortDate(addDays(today, SPAN - 1))}</span>
      </div>

      {shown.length === 0 && <p className="cal-empty">Nothing matches in the next {SPAN} days.</p>}

      {grid.map((w) => (
        <section key={w.start} className="cal-week" aria-label={`Week of ${shortDate(w.start)}`}>
          <h2 className="cal-week-h">Week of {shortDate(w.start)}</h2>
          <ol className="cal-days">
            {w.days.map((d) => {
              const past = d.date < today;
              const out = d.date > addDays(today, SPAN - 1);
              return (
                <li key={d.date} className={`cal-day${d.date === today ? " is-today" : ""}${past || out ? " is-off" : ""}${d.items.length === 0 ? " is-empty" : ""}`}>
                  <p className="cal-day-h">
                    <span>{weekday(d.date)}</span> <span>{shortDate(d.date)}</span>
                  </p>
                  <ul>
                    {d.items.map((r) => {
                      const k = kindOf(r.kind);
                      const ours = r.source === "corpus";
                      return (
                        <li key={`${d.date}-${r.id}`} className="cal-item">
                          <span className={`cal-glyph cal-k-${r.kind}`} title={k.label}>
                            <Glyph name={k.glyph} size={13} />
                          </span>
                          <span className="cal-item-t">
                            {ours ? (
                              <span title={`${k.label}, ${confidenceWord(r.confidence, true)}`}>{r.title}</span>
                            ) : (
                              <a href={r.source_url} className="cal-link" rel="noopener noreferrer" title={`${k.label}, ${confidenceWord(r.confidence, false)}`}>
                                {r.title}
                              </a>
                            )}
                            {ours && <span className="cal-flag"> unconfirmed</span>}
                            {r.end_date && r.end_date > r.on_date && <span className="cal-flag"> until {shortDate(r.end_date)}</span>}
                          </span>
                          <IsoFlags codes={r.countries.slice(0, 3)} />
                        </li>
                      );
                    })}
                  </ul>
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </div>
  );
}
