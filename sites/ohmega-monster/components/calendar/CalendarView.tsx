"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import IsoFlags from "@/components/IsoFlags";
import Glyph from "@/components/vl/Glyph";
import {
  addDays, addMonths, countriesOf, filterRows, GRADE_WORD, horizon, IMPORTANCE_WORD, indexByDay, isUnconfirmed, kindOf, monthGrid, NO_FILTER, shortDate,
  situationLabel, sourceLabel, toComing, TOPICS, weekday, weekStart, type CalendarRow, type CalendarTopic,
} from "@/lib/calendar-shared";
import { countryName } from "@/lib/flags";

import ComingStrip from "./ComingStrip";
import "./calendar.css";

// The /calendar page's body. An "on the horizon" strip for the next 72 hours, then the whole window (14 days back, 180 ahead) in one of three
// views: week (default; seven day columns, an agenda on a phone), month (a grid, three items a cell) or list (every item with its detail).
// Filters: topic chips, country, situation, and a switch for routine items (hidden by default). Receives plain rows and today's date from the
// server page; imports only pure shared files (no server-only modules). A date is a plan: unconfirmed and estimated items say so.

type Row = Required<CalendarRow>;
type View = "week" | "month" | "list";
const VIEWS: { id: View; label: string }[] = [{ id: "month", label: "Month" }, { id: "list", label: "Feed" }];   // week view dropped (operator, 2026-10-25)
const CELL_MAX = 3;

/** Three small bars: how many are filled is the importance (1 routine, 2 notable, 3 major). */
function Importance({ n }: { n: number }) {
  return (
    <span className="cal-imp" role="img" aria-label={`importance: ${IMPORTANCE_WORD[n]}`} title={`importance: ${IMPORTANCE_WORD[n]}`}>
      {[1, 2, 3].map((i) => (
        <span key={i} className={i <= n ? "is-on" : ""} />
      ))}
    </span>
  );
}

function Title({ r }: { r: Row }) {
  const ours = isUnconfirmed(r);
  return ours ? (
    <span>{r.title}</span>
  ) : (
    <a href={r.source_url} className="cal-link" rel="noopener noreferrer">
      {r.title}
    </a>
  );
}

/** One item in a day cell: kind glyph, title, a flag when it is not an official date, flags of its countries. */
function Compact({ r }: { r: Row }) {
  const k = kindOf(r.kind);
  const ours = isUnconfirmed(r);
  return (
    <li className={`cal-item cal-imp-${r.importance}`}>
      <span className={`cal-glyph cal-k-${r.kind}`} title={k.label}>
        <Glyph name={k.glyph} size={13} />
      </span>
      <span className="cal-item-t" title={`${k.label}; ${GRADE_WORD[r.grade]}; importance ${IMPORTANCE_WORD[r.importance]}`}>
        <Title r={r} />
        {ours ? <span className="cal-flag"> unconfirmed</span> : r.grade === "estimated" ? <span className="cal-flag"> estimated</span> : null}
        {r.end_date && r.end_date > r.on_date && <span className="cal-flag"> until {shortDate(r.end_date)}</span>}
      </span>
      <IsoFlags codes={r.countries.slice(0, 3)} />
    </li>
  );
}

/** One row of the list view: everything we know about the item, each link a way to check it. */
function Detailed({ r, past }: { r: Row; past: boolean }) {
  const k = kindOf(r.kind);
  const ours = isUnconfirmed(r);
  return (
    <li className={`cal-line${past ? " is-past" : ""}`}>
      <span className={`cal-glyph cal-k-${r.kind}`} title={k.label}>
        <Glyph name={k.glyph} size={14} />
      </span>
      <div className="cal-line-b">
        <p className="cal-line-t">
          <Title r={r} />
          {r.end_date && r.end_date > r.on_date && <span className="cal-flag"> until {shortDate(r.end_date)}</span>}
        </p>
        <p className="cal-meta">
          <span>{k.label}</span>
          <Importance n={r.importance} />
          <span className={ours || r.grade === "estimated" ? "cal-flag" : ""}>{ours ? GRADE_WORD.unconfirmed : GRADE_WORD[r.grade]}</span>
          {r.sources.map((s) => (
            <a key={s.source} href={s.url} className="cal-link" rel="noopener noreferrer">
              {sourceLabel(s.source)}
            </a>
          ))}
          {r.countries.slice(0, 4).map((c) => (
            <Link key={c} href={`/intel/actors/${c}`} className="cal-link">
              {countryName(c)}
            </Link>
          ))}
          {r.situations.slice(0, 2).map((s) => (
            <Link key={s} href={`/situations/${s}`} className="cal-link">
              {situationLabel(s)}
            </Link>
          ))}
        </p>
      </div>
    </li>
  );
}

export default function CalendarView({ rows, today }: { rows: Row[]; today: string }) {
  const [view, setView] = useState<View>("month");
  const [topics, setTopics] = useState<Set<CalendarTopic>>(new Set());
  const [country, setCountry] = useState("");
  const [situation, setSituation] = useState("");
  const [routine, setRoutine] = useState(false);
  const [past, setPast] = useState(false);
  const [anchor, setAnchor] = useState(`${today.slice(0, 7)}-01`);

  const present = useMemo(() => new Set(rows.map((r) => r.topic)), [rows]);
  const countries = useMemo(() => countriesOf(rows), [rows]);
  const situations = useMemo(() => Array.from(new Set(rows.flatMap((r) => r.situations))).sort(), [rows]);
  const filter = useMemo(() => ({ ...NO_FILTER, topics, country, situation, routine }), [topics, country, situation, routine]);
  const shown = useMemo(() => filterRows(rows, filter), [rows, filter]);
  const soon = useMemo(() => horizon(shown.filter((r) => (r.end_date ?? r.on_date) >= today), today), [shown, today]);
  const byDay = useMemo(() => indexByDay(shown), [shown]);
  const month = useMemo(() => monthGrid(shown, anchor), [shown, anchor]);
  const hidden = useMemo(() => filterRows(rows, { ...filter, routine: true }).length - shown.length, [rows, filter, shown]);

  const toggle = (t: CalendarTopic) =>
    setTopics((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  const step = (dir: -1 | 1) => setAnchor(view === "month" ? addMonths(anchor, dir) : addDays(anchor, 7 * dir));
  const goToday = () => setAnchor(view === "month" ? `${today.slice(0, 7)}-01` : weekStart(today));
  const pick = (v: View) => {
    setView(v);
    setAnchor(v === "month" ? `${anchor.slice(0, 7)}-01` : weekStart(anchor));
  };

  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(anchor, i));
  const listDays = useMemo(() => {
    const lo = past ? addDays(today, -14) : today;
    const map = new Map<string, Row[]>();
    for (const r of shown) {
      const d = r.on_date < lo ? ((r.end_date ?? r.on_date) >= lo ? lo : "") : r.on_date;
      if (d) map.set(d, [...(map.get(d) ?? []), r]);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [shown, today, past]);

  return (
    <div className="cal-view">
      <ComingStrip rows={soon.map(toComing)} today={today} heading="On the horizon, next 72 hours" limit={6} all={false} dense />

      <div className="cal-filters" role="group" aria-label="Filter the calendar">
        <ul className="cal-chips">
          {TOPICS.filter((t) => present.has(t.id)).map((t) => (
            <li key={t.id}>
              <button type="button" className={`cal-chip${topics.has(t.id) ? " is-on" : ""}`} aria-pressed={topics.has(t.id)} onClick={() => toggle(t.id)}>
                {t.label}
              </button>
            </li>
          ))}
        </ul>
        <div className="cal-selects">
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
          {situations.length > 0 && (
            <label className="cal-country">
              <span className="vl-label">Situation</span>
              <select value={situation} onChange={(e) => setSituation(e.target.value)}>
                <option value="">All</option>
                {situations.map((s) => (
                  <option key={s} value={s}>
                    {situationLabel(s)}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="cal-check">
            <input type="checkbox" checked={routine} onChange={(e) => setRoutine(e.target.checked)} />
            <span>Routine items{hidden > 0 && !routine ? ` (${hidden} hidden)` : ""}</span>
          </label>
        </div>
      </div>

      <div className="cal-bar-row">
        <div className="cal-views" role="group" aria-label="View">
          {VIEWS.map((v) => (
            <button key={v.id} type="button" className={`cal-chip${view === v.id ? " is-on" : ""}`} aria-pressed={view === v.id} onClick={() => pick(v.id)}>
              {v.label}
            </button>
          ))}
        </div>
        {view !== "list" ? (
          <div className="cal-nav" role="group" aria-label="Move through time">
            <button type="button" className="cal-chip" onClick={() => step(-1)} aria-label={view === "month" ? "Previous month" : "Previous week"}>
              ←
            </button>
            <span className="cal-nav-l">{view === "month" ? month.label : `Week of ${shortDate(anchor)}`}</span>
            <button type="button" className="cal-chip" onClick={() => step(1)} aria-label={view === "month" ? "Next month" : "Next week"}>
              →
            </button>
            <button type="button" className="cal-chip" onClick={goToday}>
              Today
            </button>
          </div>
        ) : (
          <label className="cal-check">
            <input type="checkbox" checked={past} onChange={(e) => setPast(e.target.checked)} />
            <span>Include the past 14 days</span>
          </label>
        )}
        <span className="cal-count">{shown.length} items</span>
      </div>

      {shown.length === 0 && <p className="cal-empty">Nothing matches these filters.</p>}

      {view === "week" && (
        <ol className="cal-days" aria-label={`Week of ${shortDate(anchor)}`}>
          {weekDays.map((d) => {
            const items = (byDay.get(d) ?? []).slice().sort((a, b) => b.importance - a.importance || a.title.localeCompare(b.title));
            return (
              <li key={d} className={`cal-day${d === today ? " is-today" : ""}${d < today ? " is-off" : ""}${items.length === 0 ? " is-empty" : ""}`}>
                <p className="cal-day-h">
                  <span>{weekday(d)}</span> <span>{shortDate(d)}</span>
                </p>
                <ul>
                  {items.map((r) => (
                    <Compact key={`${d}-${r.id}`} r={r} />
                  ))}
                </ul>
              </li>
            );
          })}
        </ol>
      )}

      {view === "month" && (
        <div className="cal-month" aria-label={month.label}>
          <p className="cal-month-h" aria-hidden="true">
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((w) => (
              <span key={w}>{w}</span>
            ))}
          </p>
          {month.weeks.map((w) => (
            <ol key={w[0].date} className="cal-days cal-days-m">
              {w.map((c) => (
                <li key={c.date} className={`cal-day${c.date === today ? " is-today" : ""}${!c.inMonth || c.date < today ? " is-off" : ""}${c.items.length === 0 ? " is-empty" : ""}`}>
                  <p className="cal-day-h">
                    <span className="cal-day-w">{weekday(c.date)}</span> <span>{+c.date.slice(8, 10)}</span>
                  </p>
                  <ul>
                    {c.items.slice(0, CELL_MAX).map((r) => (
                      <Compact key={`${c.date}-${r.id}`} r={r} />
                    ))}
                  </ul>
                  {c.items.length > CELL_MAX && (
                    <button type="button" className="cal-more" onClick={() => setView("list")}>
                      +{c.items.length - CELL_MAX} more
                    </button>
                  )}
                </li>
              ))}
            </ol>
          ))}
        </div>
      )}

      {view === "list" &&
        listDays.map(([d, items]) => (
          <section key={d} className="cal-week" aria-label={shortDate(d)}>
            <h2 className="cal-week-h">
              {weekday(d)} {shortDate(d)}
              {d === today ? " · today" : ""}
            </h2>
            <ul className="cal-lines">
              {items
                .slice()
                .sort((a, b) => b.importance - a.importance || a.title.localeCompare(b.title))
                .map((r) => (
                  <Detailed key={r.id} r={r} past={d < today} />
                ))}
            </ul>
          </section>
        ))}
    </div>
  );
}
