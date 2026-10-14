"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";

import { whenUtc, type LiveEvent } from "@/lib/live-shared";

import { eventItem, safeUrl } from "./liveItems";
import { publishEvents, requestShow, useScope } from "./theaterLive";

// The "Live now" strip of a theater or dossier (client half of LiveParts.tsx). It lists the live events the server matched to the
// theater, hands the same events to the theater's map (theaterLive.ts) and, while that map is up, gives each located event a
// "Show me": the map flies there and opens the popup, without leaving the page. The link to /live stays as the second route.

export default function LiveNowStrip({ events, scope }: { events: LiveEvent[]; scope: string }) {
  const items = useMemo(() => events.map(eventItem), [events]);
  const { map } = useScope(scope);

  useEffect(() => {
    publishEvents(scope, items);
    return () => publishEvents(scope, []);
  }, [scope, items]);

  return (
    <aside className="live-now" aria-label="Live now">
      <p className="live-now-head">
        Live now <Link href="/live" className="xt">all live data →</Link>
      </p>
      <ul>
        {events.map((e, i) => {
          const url = safeUrl(e.source_url);
          const located = map && e.lat !== null && e.lon !== null;
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
                {located && (
                  <>
                    {" "}
                    <button type="button" className="live-showme" onClick={() => requestShow(scope, items[i].id)} aria-label={`Show on the map: ${e.title}`}>
                      Show me
                    </button>
                  </>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
