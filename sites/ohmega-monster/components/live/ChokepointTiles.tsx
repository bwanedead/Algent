import type { GateNow, Tile } from "@/lib/live-shared";

// The chokepoint tiles: ships in the strait RIGHT NOW (live, from the vessel board), crossings so far today (running count), and
// the last completed day against its recent usual (Ohmega's own count). Tapping a tile frames the strait on the map ("focus").
// Client-safe (props only; no store imports).

function Bar({ tile }: { tile: Tile }) {
  // The track is the usual day (100%); the fill is the last full day against it, capped at twice usual. No axis, no key.
  const ratio = tile.usual && tile.usual > 0 ? Math.min(2, tile.latest / tile.usual) : null;
  return (
    <div className="live-bar" aria-hidden="true">
      <span className="live-bar-usual" />
      {ratio !== null && <span className={`live-bar-fill${ratio < 0.7 ? " is-low" : ""}`} style={{ width: `${(ratio / 2) * 100}%` }} />}
    </div>
  );
}

export default function ChokepointTiles({ tiles, gates, focus, onFocus, fresh }: {
  tiles: Tile[];
  gates: Record<string, GateNow>;
  focus: string | null;
  onFocus: (slug: string | null) => void;
  fresh: string;
}) {
  const slugs = Object.keys(gates);
  if (slugs.length === 0 && tiles.length === 0) {
    return <p className="live-empty">Ship counts start once our own ship-position feed is running. Until then the IMF PortWatch weekly figures stay in each theater&apos;s numbers.</p>;
  }
  const byRegion = new Map(tiles.map((t) => [t.region, t]));
  return (
    <>
      <ul className="live-tiles">
        {slugs.map((slug) => {
          const g = gates[slug];
          const t = byRegion.get(slug);
          const on = focus === slug;
          return (
            <li key={slug} className={`live-tile${on ? " is-on" : ""}`}>
              <button type="button" className="live-tile-btn" aria-pressed={on} onClick={() => onFocus(on ? null : slug)}>
                <span className="live-tile-name">{g.label}</span>
                <span className="live-tile-num">
                  <strong>{typeof g.in_strait === "number" ? g.in_strait : "–"}</strong> <span className="live-muted">in the strait now</span>
                </span>
                <span className="live-tile-note">
                  {typeof g.moving === "number" ? `${g.moving} moving` : ""}
                  {typeof g.tankers === "number" ? ` · ${g.tankers} tankers` : ""}
                  {typeof g.transits_today === "number" ? ` · ${g.transits_today} crossed today so far` : ""}
                </span>
                {t && <Bar tile={t} />}
                <span className="live-tile-note">
                  {t
                    ? t.usual !== null
                      ? `${t.latest} on ${t.latestDay.slice(5)}, usual about ${Math.round(t.usual)}${t.pct !== null && Math.abs(t.pct) >= 1 ? ` (${t.pct > 0 ? "+" : "−"}${Math.abs(t.pct)}%)` : ""}`
                      : `${t.latest} on ${t.latestDay.slice(5)}; building a normal`
                    : "no completed day yet"}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="live-note">Tap a tile to frame the strait on the map with the ships near it and their trails. {fresh && `Live counts updated ${fresh}.`}</p>
    </>
  );
}
