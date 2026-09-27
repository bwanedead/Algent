import Link from "next/link";

import { getMenus, menuLabel } from "@/lib/radar";

// The newest headline-radar menu, pinned above the feed — the nav item alone was easy to miss.
export default function RadarCard() {
  const m = getMenus()[0];
  if (!m) return null;
  const preview = m.leads.slice(0, 4);
  return (
    <Link href="/radar" className="radar-card" aria-label="Open the headline radar">
      <div className="radar-card-head">
        <span className="radar-card-kicker">Headline radar</span>
        <span className="radar-card-when">{menuLabel(m)} · {m.leads.length} headlines</span>
      </div>
      <ul>
        {preview.map((l) => (
          <li key={l.n}>{l.title}</li>
        ))}
      </ul>
      <span className="radar-card-foot">
        As other outlets reported it — not yet verified by us. See all {m.leads.length} and earlier editions →
      </span>
    </Link>
  );
}
