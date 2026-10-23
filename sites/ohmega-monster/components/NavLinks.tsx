"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// The primary navigation, one level, always visible (it wraps on a phone; nothing hides behind a menu): the five places the site is
// made of (docs/architecture/information-architecture.md §3). The logo is Home. Each page belongs to exactly one place, so the
// current one is always marked: Daily (a desk's report and its headlines), Situations (the living files, and the briefs that are
// dated entries of them), Articles, Globe, and Data (every measured layer and judgment, whatever its own route is called).
const startsWith = (...prefixes: string[]) => (p: string) => prefixes.some((x) => p === x || p.startsWith(`${x}/`));
const isDaily = startsWith("/daily", "/intel/events");
const isSituation = startsWith("/situations", "/intel/briefs");
const isArticle = startsWith("/articles");
const isGlobe = startsWith("/globe");

const LINKS: { href: string; label: string; match: (p: string) => boolean }[] = [
  { href: "/daily", label: "Daily", match: isDaily },
  { href: "/situations", label: "Situations", match: isSituation },
  { href: "/articles", label: "Articles", match: isArticle },
  { href: "/globe", label: "Globe", match: isGlobe },
  // Data is everything else that is not Home: the hub, the tool routes under /intel, Pulses, the calendar, the live map, the developers' page.
  { href: "/calendar", label: "Calendar", match: (p) => p.startsWith("/calendar") },
  { href: "/explore", label: "Explore", match: (p) => p !== "/" && !p.startsWith("/calendar") && ![isDaily, isSituation, isArticle, isGlobe].some((m) => m(p)) },
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
