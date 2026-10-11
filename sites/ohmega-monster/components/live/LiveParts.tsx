import Link from "next/link";

import { liveEvents, liveTouching, whenUtc, type LiveEvent, type Tile } from "@/lib/live";

import "@/app/live/live.css";

// Server components of the live surfaces: the chokepoint tiles (yesterday against the recent normal, one plain bar) and
// the "Live now" strip that theater sections and dossiers show when a live event touches their countries.

const safeUrl = (u: string) => (/^https?:\/\//.test(u) ? u : "");

function Bar({ tile }: { tile: Tile }) {
  // The track is the usual day (100%); the fill is yesterday against it, capped at twice usual. No axis, no key.
  const ratio = tile.usual && tile.usual > 0 ? Math.min(2, tile.latest / tile.usual) : null;
  return (
    <div className="live-bar" aria-hidden="true">
      <span className="live-bar-usual" />
      {ratio !== null && <span className={`live-bar-fill${ratio < 0.7 ? " is-low" : ""}`} style={{ width: `${(ratio / 2) * 100}%` }} />}
    </div>
  );
}

export function ChokepointTiles({ tiles }: { tiles: Tile[] }) {
  if (tiles.length === 0) {
    return <p className="live-empty">Ship counts start once our own ship-position feed is running. Until then the IMF PortWatch weekly figures stay in each theater&apos;s numbers.</p>;
  }
  return (
    <ul className="live-tiles">
      {tiles.map((t) => (
        <li key={t.region} className="live-tile">
          <p className="live-tile-name">{t.name}</p>
          <p className="live-tile-num">
            <strong>{t.latest}</strong> <span className="live-muted">ships on {t.latestDay.slice(5)}</span>
          </p>
          <Bar tile={t} />
          <p className="live-tile-note">
            {t.usual !== null ? (
              <>
                usual about {Math.round(t.usual)}
                {t.pct !== null && Math.abs(t.pct) >= 1 ? ` (${t.pct > 0 ? "+" : "−"}${Math.abs(t.pct)}%)` : ""}
              </>
            ) : (
              "building a normal: needs a few more days"
            )}
            {t.tankers !== null && ` · ${t.tankers} tankers`}
          </p>
        </li>
      ))}
    </ul>
  );
}

function stripLine(e: LiveEvent) {
  const url = safeUrl(e.source_url);
  return (
    <li key={e.id}>
      <span className={`live-dot live-dot-${e.kind}`} aria-hidden="true" />
      <span>
        {e.title}
        {e.starts_at && e.kind !== "aircraft" ? <span className="live-muted"> · since {whenUtc(e.starts_at)}</span> : null}
        {url && (
          <>
            {" "}
            <a className="xt" href={url} target="_blank" rel="noopener noreferrer">{e.source}</a>
          </>
        )}
      </span>
    </li>
  );
}

/** "Live now": renders nothing unless a current live event touches a country the text names. */
export async function LiveNow({ text }: { text: string }) {
  const touching = liveTouching(await liveEvents(), text);
  if (touching.length === 0) return null;
  return (
    <aside className="live-now" aria-label="Live now">
      <p className="live-now-head">
        Live now <Link href="/live" className="xt">all live data →</Link>
      </p>
      <ul>{touching.map(stripLine)}</ul>
    </aside>
  );
}
