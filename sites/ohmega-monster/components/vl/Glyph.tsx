import type { ReactNode } from "react";

// The site's glyph set: simple 24x24 line icons (stroke follows `currentColor`), one per category and per kind of object, plus four
// filled direction marks. Pure SVG, no dependencies, safe in server and client components. Decorative by default: the words (or a
// `title`) travel beside it, so a glyph never carries a meaning alone.

export type GlyphName =
  // categories
  | "conflict" | "economy" | "politics" | "energy" | "disaster"
  // objects
  | "country" | "theater" | "ship" | "tanker" | "aircraft" | "plant" | "event" | "fire" | "outage" | "quake" | "actor"
  // places in the site
  | "globe" | "live" | "pulse" | "record" | "article" | "radar"
  // direction (filled)
  | "up" | "down" | "steady" | "unclear";

type FilledName = "up" | "down" | "steady" | "unclear";

const LINE: Record<Exclude<GlyphName, FilledName>, ReactNode> = {
  conflict: (<><circle cx="12" cy="12" r="6" /><path d="M12 2v5M12 17v5M2 12h5M17 12h5" /></>),
  economy: <path d="M4 20h16M7 20v-7M12 20V6M17 20v-10" />,
  politics: <path d="M3 9l9-5 9 5M5 9v9M9.5 9v9M14.5 9v9M19 9v9M3 20h18" />,
  energy: <path d="M13 2L5 14h6l-1 8 8-12h-6z" />,
  disaster: (<><path d="M12 3l10 18H2z" /><path d="M12 10v5M12 18v.5" /></>),
  country: <path d="M5 21V4M5 4h11l-2 4 2 4H5" />,
  theater: (<><path d="M12 21s-7-6.2-7-11a7 7 0 0114 0c0 4.8-7 11-7 11z" /><circle cx="12" cy="10" r="2.5" /></>),
  ship: <path d="M2 16l2.5 4h15L22 16zM6 16v-5h12v5M10 11V6h4v5" />,
  tanker: <path d="M12 3s6 6.5 6 11a6 6 0 01-12 0c0-4.5 6-11 6-11z" />,
  aircraft: <path d="M21 14l-8-4V4.5a1.5 1.5 0 00-3 0V10l-8 4v2l8-2v4l-2 1.5V21l3.5-1 3.5 1v-1.5L13 18v-4l8 2z" />,
  plant: <path d="M3 21V11l6 4v-4l6 4V5h5v16zM7 18h2M12 18h2" />,
  event: <path d="M12 3l2.2 5.3 5.8.5-4.4 3.8 1.4 5.6L12 15l-5 3.2 1.4-5.6L4 8.8l5.8-.5z" />,
  fire: <path d="M12 3c1 4 5 5 5 10a5 5 0 01-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-6 1-9z" />,
  outage: (<><circle cx="12" cy="12" r="8" /><path d="M6 6l12 12" /></>),
  quake: (<><circle cx="12" cy="12" r="2" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="10" /></>),
  actor: (<><circle cx="12" cy="8" r="3.5" /><path d="M5 21c0-4 3-6.5 7-6.5s7 2.5 7 6.5" /></>),
  globe: (<><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></>),
  live: (<><circle cx="12" cy="12" r="2" /><path d="M7.5 7.5a6.4 6.4 0 000 9M16.5 7.5a6.4 6.4 0 010 9M4.5 4.5a10.6 10.6 0 000 15M19.5 4.5a10.6 10.6 0 010 15" /></>),
  pulse: <path d="M2 12h4l2-6 4 12 2-6h8" />,
  record: <path d="M4 5h16v11H9l-5 4z" />,
  article: <path d="M6 3h9l4 4v14H6zM15 3v4h4M9 12h7M9 16h7" />,
  radar: (<><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4.5" /><path d="M12 12L18 6" /></>),
};

const FILLED: Record<FilledName, ReactNode> = {
  up: <path d="M12 4l8 14H4z" />,
  down: <path d="M12 20L4 6h16z" />,
  steady: <path d="M12 5l7 7-7 7-7-7z" />,
  unclear: <circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="3 3" />,
};

const isFilled = (n: GlyphName): n is FilledName => n === "up" || n === "down" || n === "steady" || n === "unclear";

export default function Glyph({ name, size = 20, title, className }: { name: GlyphName; size?: number; title?: string; className?: string }) {
  const filled = isFilled(name);
  return (
    <svg
      className={`vl-glyph${className ? ` ${className}` : ""}`}
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill={filled ? "currentColor" : "none"}
      stroke={filled ? "none" : "currentColor"}
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {title && <title>{title}</title>}
      {isFilled(name) ? FILLED[name] : LINE[name]}
    </svg>
  );
}
