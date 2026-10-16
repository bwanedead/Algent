import Link from "next/link";

// The one breadcrumb for every deep page: the trail back up ("Intelligence / Theaters"). The page's own
// name is not repeated (its heading is right below). Styled by `.th-crumb` (app/intel/theaters/theaters.css).
export default function Crumbs({ trail }: { trail: { href: string; label: string }[] }) {
  return (
    <nav className="th-crumb" aria-label="Breadcrumb">
      {trail.map((c, i) => (
        <span key={c.href}>
          {i > 0 && <span aria-hidden="true"> / </span>}
          <Link href={c.href}>{c.label}</Link>
        </span>
      ))}
    </nav>
  );
}

export const INTEL_CRUMB = { href: "/intel", label: "Intelligence" } as const;
export const THEATERS_CRUMB = { href: "/intel/theaters", label: "Theaters" } as const;
export const ACTORS_CRUMB = { href: "/intel/actors", label: "Actors" } as const;
