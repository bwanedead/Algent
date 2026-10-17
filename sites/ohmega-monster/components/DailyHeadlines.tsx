import Link from "next/link";

import { getMenus, hostOf, menuLabel } from "@/lib/radar";

import "./pagetag.css";

// "Today's headlines": the newest Headlines edition as a collapsed strip inside the Daily. It is the unverified
// wire, so it sits closed, under the report, labelled as such; the full list lives at /headlines.
export default async function DailyHeadlines() {
  const menu = (await getMenus())[0];
  if (!menu) return null;
  return (
    <details className="dh">
      <summary>
        <span className="dh-k">Today&apos;s headlines</span> <span className="dh-n">{menu.leads.length}</span>
        <span className="dh-note"> · other outlets, not verified · {menuLabel(menu)}</span>
      </summary>
      <ol className="dh-list">
        {menu.leads.map((l) => (
          <li key={l.n}>
            <span className="dh-t">{l.title}</span>
            {l.sources[0] && (
              <a href={l.sources[0]} target="_blank" rel="noopener noreferrer nofollow" className="dh-src">
                {hostOf(l.sources[0])} ↗
              </a>
            )}
          </li>
        ))}
      </ol>
      <p className="dh-all"><Link href="/headlines">All headlines and earlier editions →</Link></p>
    </details>
  );
}
