import Link from "next/link";

import { daily, dayHref, dayInMonth, monthLabel } from "@/lib/daily";

// Every day with a report, newest first, grouped by month. The day is the handle; the headline is one
// clipped line. Lives inside the day navigator's "All days" popover; the current day is the one highlight.
export default async function DailyArchive({ dates, current, domain, base }: { dates: string[]; current: string; domain: string; base: string }) {
  if (dates.length === 0) return null;
  const headlines = await Promise.all(dates.map(async (d) => (await daily(domain, d))?.headline || "Daily report"));
  const lineOf = new Map(dates.map((d, i) => [d, headlines[i]]));
  const months: { key: string; label: string; days: string[] }[] = [];
  for (const d of dates) {
    const key = d.slice(0, 7);
    const last = months[months.length - 1];
    if (last && last.key === key) last.days.push(d);
    else months.push({ key, label: monthLabel(d), days: [d] });
  }
  return (
    <div className="geo-pd geo-archive">
      <p className="geo-pd-title">All days</p>
      {months.map((m) => (
        <section key={m.key} className="geo-arch-month" aria-label={m.label}>
          <h3 className="geo-h2">{m.label}</h3>
          <ul>
            {m.days.map((d) => {
              const here = d === current;
              return (
                <li key={d}>
                  <Link href={dayHref(base, d, dates)} className={here ? "is-here" : undefined} aria-current={here ? "page" : undefined}>
                    <time className="geo-arch-day" dateTime={d}>
                      {dayInMonth(d)}
                    </time>
                    <span className="geo-arch-line">{lineOf.get(d)}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
