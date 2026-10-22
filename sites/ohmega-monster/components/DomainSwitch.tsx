import Link from "next/link";

import { DESKS, dailyBase } from "@/lib/desks";

// The Daily comes in one edition per desk; this is the switch at the top of each ("All dailies · Geopolitics · AI"), generated from
// the desk list so a new desk appears here by itself. Plain links to each desk's newest report (the pages handle a desk with no report
// yet). Server component, no state.
export default function DomainSwitch({ current }: { current: string }) {
  return (
    <nav className="geo-domains" aria-label="Daily edition">
      <Link href="/daily" className="geo-domain">All dailies</Link>
      {DESKS.map((d) =>
        d.id === current ? (
          <span key={d.id} className="geo-domain is-on" aria-current="page">{d.label}</span>
        ) : (
          <Link key={d.id} href={dailyBase(d.id)} className="geo-domain">{d.label}</Link>
        ),
      )}
    </nav>
  );
}
