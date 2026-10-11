import Link from "next/link";

import { liveEvents, liveTouching, whenUtc, type LiveEvent } from "@/lib/live";

import "@/app/live/live.css";

// Server components of the live surfaces: the "Live now" strip that theater sections and dossiers show when a live event touches their countries.

const safeUrl = (u: string) => (/^https?:\/\//.test(u) ? u : "");

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
