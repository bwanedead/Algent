import type { Headline, LiveWorld } from "@/lib/live-shared";

// A postage-stamp world for Home: the land as one quiet shape, one dot per live headline in its layer's colour. Pure SVG on the server, no
// script, no interaction (the whole strip links to /live, where the real map lives). Draws nothing without the basemap.

const LAYER_VAR: Record<Headline["layer"], string> = { ships: "--vl-l-ship", aircraft: "--vl-l-air", fire: "--vl-l-fire", outage: "--vl-l-outage", quake: "--vl-l-quake" };

export default function LiveMiniMap({ world, headlines }: { world: LiveWorld | null; headlines: Headline[] }) {
  if (!world) return null;
  const [w, s, e, n] = world.bbox;
  const land = world.countries.map((c) => c.d).join(" ");
  const dots = headlines.flatMap((h) => {
    if (h.lat === null || h.lon === null || h.lon < w || h.lon > e || h.lat < s || h.lat > n) return [];
    return [{ id: h.id, layer: h.layer, x: ((h.lon - w) / (e - w)) * world.width, y: ((n - h.lat) / (n - s)) * world.height }];
  });
  const r = world.width / 70;
  return (
    <svg className="hm-minimap" viewBox={`0 0 ${world.width} ${world.height}`} role="img" aria-label={`World map with ${dots.length} live signals marked`} preserveAspectRatio="xMidYMid meet">
      <rect width={world.width} height={world.height} className="hm-minimap-sea" />
      <path d={land} className="hm-minimap-land" />
      {dots.map((d) => (
        <g key={d.id} style={{ color: `var(${LAYER_VAR[d.layer]})` }}>
          <circle cx={d.x} cy={d.y} r={r * 2.4} fill="currentColor" opacity="0.22" />
          <circle cx={d.x} cy={d.y} r={r} fill="currentColor" />
        </g>
      ))}
    </svg>
  );
}
