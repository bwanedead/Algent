import Link from "next/link";

import type { Door } from "@/lib/sections";

import "./doors.css";

// A grid of doors into the site: a title, one line, and a quiet live hint. Used by Home and by the
// Intelligence directory. Each door is one whole link, so it is easy to hit on a phone.
export default function Doors({ doors, label }: { doors: Door[]; label: string }) {
  return (
    <ul className="doors" aria-label={label}>
      {doors.map((d) => (
        <li key={d.href}>
          <Link href={d.href} className="door">
            <span className="door-title">{d.title}</span>
            <span className="door-line">{d.line}</span>
            {d.hint && <span className="door-hint">{d.hint}</span>}
            <span className="door-go" aria-hidden="true">→</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
