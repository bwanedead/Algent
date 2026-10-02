import Link from "next/link";

import { daily, shortDay } from "@/lib/daily";

// Earlier days: a compact list, newest first. The date is the handle; the headline is one clipped line.
export default function DailyArchive({ dates, domain, href }: { dates: string[]; domain: string; href: string }) {
  if (dates.length === 0) return null;
  return (
    <nav className="geo-archive" aria-label="Earlier days">
      <h2 className="geo-h2">Earlier days</h2>
      <ul>
        {dates.map((d) => {
          const r = daily(domain, d);
          return (
            <li key={d}>
              <Link href={`${href}/${d}`}>
                <time className="geo-micro" dateTime={d}>
                  {shortDay(d)} {d.slice(0, 4)}
                </time>
                <span className="geo-arch-line">{r?.headline || "Daily report"}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
