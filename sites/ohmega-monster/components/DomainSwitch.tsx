import Link from "next/link";

// The Daily comes in one edition per domain; this is the two-way switch at the top of each, "Geopolitics · AI". Plain links to each domain's newest report
// (the pages themselves handle a domain with no report yet). Server component, no state.
const DOMAINS = [
  { id: "geopolitics", href: "/geopolitics", label: "Geopolitics" },
  { id: "ai", href: "/ai", label: "AI" },
] as const;

export default function DomainSwitch({ current }: { current: (typeof DOMAINS)[number]["id"] }) {
  return (
    <nav className="geo-domains" aria-label="Daily edition">
      {DOMAINS.map((d) =>
        d.id === current ? (
          <span key={d.id} className="geo-domain is-on" aria-current="page">{d.label}</span>
        ) : (
          <Link key={d.id} href={d.href} className="geo-domain">{d.label}</Link>
        ),
      )}
    </nav>
  );
}
