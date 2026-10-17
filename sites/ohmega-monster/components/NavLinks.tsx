"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// The primary navigation, one level, always visible (it wraps on a phone; nothing hides behind a menu): the three
// products (Daily, Theaters, Articles), the live map, and Intelligence, the door to every data tool (Pulses, the
// record, calendar, sanctions, maritime, graph, actors, headlines). The current section is marked.
const TOOL_PREFIXES = ["/intel", "/pulses", "/calendar", "/headlines", "/globe"];
const LINKS: { href: string; label: string; match: (p: string) => boolean }[] = [
  { href: "/", label: "Home", match: (p) => p === "/" },
  { href: "/geopolitics", label: "Daily", match: (p) => p.startsWith("/geopolitics") },
  { href: "/intel/theaters", label: "Theaters", match: (p) => p.startsWith("/intel/theaters") },
  { href: "/articles", label: "Articles", match: (p) => p.startsWith("/articles") },
  { href: "/live", label: "Live", match: (p) => p.startsWith("/live") },
  { href: "/intel", label: "Intelligence", match: (p) => !p.startsWith("/intel/theaters") && TOOL_PREFIXES.some((x) => p.startsWith(x)) },
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
