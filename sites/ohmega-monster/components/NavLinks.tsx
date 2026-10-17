"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// The primary navigation: every section of the site, one level, always visible (it wraps on a phone; nothing
// hides behind a menu). "Intelligence" is the front door to the depth pages (theaters, actors, briefs, the
// record, the situation room), so those stay one click from anywhere. The current section is marked.
const LINKS: { href: string; label: string; match: (p: string) => boolean }[] = [
  { href: "/", label: "Home", match: (p) => p === "/" },
  { href: "/articles", label: "Articles", match: (p) => p.startsWith("/articles") },
  { href: "/geopolitics", label: "Geopolitics", match: (p) => p.startsWith("/geopolitics") },
  { href: "/live", label: "Live", match: (p) => p.startsWith("/live") },
  { href: "/calendar", label: "Calendar", match: (p) => p.startsWith("/calendar") },
  { href: "/intel", label: "Intelligence", match: (p) => p.startsWith("/intel") },
  { href: "/pulses", label: "Pulses", match: (p) => p.startsWith("/pulses") },
  { href: "/radar", label: "Radar", match: (p) => p.startsWith("/radar") },
];

export default function NavLinks() {
  const path = usePathname() || "/";
  return (
    <>
      {LINKS.map((l) => {
        const here = l.match(path);
        return (
          <Link key={l.href} href={l.href} className={here ? "is-here" : undefined} aria-current={here ? "page" : undefined}>
            {l.label}
          </Link>
        );
      })}
    </>
  );
}
