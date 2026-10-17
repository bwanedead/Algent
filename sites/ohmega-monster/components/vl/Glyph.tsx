import type { ReactNode } from "react";

// The site's glyph set: thin-stroke, geometric, monoline 24x24 icons (1.4 stroke, follows `currentColor`), one per category and per
// kind of object, plus four direction marks drawn as strokes too (chevrons and a bar; nothing filled). Pure SVG, no dependencies,
// safe in server and client components. Decorative by default: the words (or a `title`) travel beside it, so a glyph never carries
// a meaning alone.

export type GlyphName =
  // categories
  | "conflict" | "economy" | "politics" | "energy" | "disaster"
  // objects
  | "country" | "theater" | "ship" | "tanker" | "aircraft" | "plant" | "event" | "fire" | "outage" | "quake" | "actor"
  // places in the site
  | "globe" | "live" | "pulse" | "record" | "article" | "radar" | "calendar" | "sanction"
  // kinds of scheduled thing
  | "ballot" | "bank" | "clock"
  // direction
  | "up" | "down" | "steady" | "unclear";

const LINE: Record<GlyphName, ReactNode> = {
  conflict: (<><circle cx="12" cy="12" r="6" /><path d="M12 2v5M12 17v5M2 12h5M17 12h5" /></>),
  economy: <path d="M4 20h16M7 20v-7M12 20V6M17 20v-10" />,
  politics: <path d="M3 9l9-5 9 5M5 9v9M9.5 9v9M14.5 9v9M19 9v9M3 20h18" />,
  energy: <path d="M13 2L5 14h6l-1 8 8-12h-6z" />,
  disaster: (<><path d="M12 3l10 18H2z" /><path d="M12 10v5M12 18v.5" /></>),
  country: <path d="M5 21V4M5 4h11l-2 4 2 4H5" />,
  theater: (<><path d="M12 21s-7-6.2-7-11a7 7 0 0114 0c0 4.8-7 11-7 11z" /><circle cx="12" cy="10" r="2.5" /></>),
  ship: <path d="M2 16l2.5 4h15L22 16zM6 16v-5h12v5M10 11V6h4v5" />,
  tanker: <path d="M3 16l2 4h14l2-4zM6 16v-3h12v3M9 13v-3M15 13v-3" />,
  aircraft: <path d="M12 3v18M4 12l8-2 8 2M8 20l4-2 4 2" />,
  plant: <path d="M3 21V11l6 4v-4l6 4V5h5v16zM7 18h2M12 18h2" />,
  event: <path d="M12 4l8 8-8 8-8-8z" />,
  fire: <path d="M5 12l7-8 7 8M5 19l7-8 7 8" />,
  outage: (<><circle cx="12" cy="12" r="8" /><path d="M6 6l12 12" /></>),
  quake: (<><circle cx="12" cy="12" r="2" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="10" /></>),
  actor: (<><circle cx="12" cy="8" r="3.5" /><path d="M5 21v-3h14v3" /></>),
  globe: (<><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></>),
  live: (<><circle cx="12" cy="12" r="2" /><path d="M7.5 7.5a6.4 6.4 0 000 9M16.5 7.5a6.4 6.4 0 010 9M4.5 4.5a10.6 10.6 0 000 15M19.5 4.5a10.6 10.6 0 010 15" /></>),
  pulse: <path d="M2 12h4l2-6 4 12 2-6h8" />,
  record: <path d="M4 5h16v11H9l-5 4zM8 9h8M8 12h5" />,
  article: <path d="M6 3h9l4 4v14H6zM15 3v4h4M9 12h7M9 16h7" />,
  radar: (<><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4.5" /><path d="M12 12L18 6" /></>),
  calendar: <path d="M4 6h16v14H4zM4 10h16M8 3v5M16 3v5M8 14h2M13 14h2M8 17h2" />,
  sanction: <path d="M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6zM8 8l8 8" />,
  ballot: <path d="M4 14h16v6H4zM7 14V9l5-3 5 3v5M10 11h4" />,
  bank: <path d="M3 9l9-5 9 5zM5 9v8M9.5 9v8M14.5 9v8M19 9v8M3 20h18M12 12v2" />,
  clock: <path d="M12 4a8 8 0 100 16 8 8 0 000-16zM12 8v4.5l3 2" />,
  up: <path d="M5 15l7-8 7 8" />,
  down: <path d="M5 9l7 8 7-8" />,
  steady: <path d="M5 12h14" />,
  unclear: <path d="M4 12h3M10.5 12h3M17 12h3" />,
};

export default function Glyph({ name, size = 20, title, className }: { name: GlyphName; size?: number; title?: string; className?: string }) {
  return (
    <svg
      className={`vl-glyph${className ? ` ${className}` : ""}`}
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      strokeLinecap="square"
      strokeLinejoin="miter"
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {title && <title>{title}</title>}
      {LINE[name]}
    </svg>
  );
}
