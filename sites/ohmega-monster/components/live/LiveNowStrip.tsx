"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import "@/app/live/live.css";

import { countText, GROUPS, NO_OBJECTS } from "./theaterObjects";
import { publishLive, requestShow, useScope } from "./theaterLive";
import { useTheaterObjects } from "./useTheaterObjects";

// The "Live now" strip of a theater or dossier: one line per kind of live object in the theater's box (military aircraft, tankers,
// military and law-enforcement vessels), counted from /live's own position feeds, and nothing else (fires, quakes and outages stay on
// /live). It loads those objects while it is near the screen (useTheaterObjects.ts), hands them to the theater's map (theaterLive.ts),
// and, while that map is up, gives each line a "Show me" that fits the map to those objects. The link to /live stays as the second route.

export default function LiveNowStrip({ bbox, scope }: { bbox: number[] | null | undefined; scope: string }) {
  const host = useRef<HTMLDivElement>(null);
  const live = useTheaterObjects(bbox, host);
  const { map, shown } = useScope(scope);

  useEffect(() => { publishLive(scope, live); }, [scope, live]);
  useEffect(() => () => publishLive(scope, NO_OBJECTS), [scope]);

  const rows = GROUPS.filter((g) => live.totals[g.key] > 0);
  return (
    <div ref={host}>
      {rows.length > 0 && (
        <aside className="live-now" aria-label="Live now">
          <p className="live-now-head">
            Live now, in this theater <Link href="/live" className="xt">all live data →</Link>
          </p>
          <ul>
            {rows.map((g) => {
              const n = live.totals[g.key];
              const drawn = live.objs.filter((o) => o.group === g.key).length;
              return (
                <li key={g.key}>
                  <span className="live-dot" style={{ color: g.color }} aria-hidden="true" />
                  <span>
                    {countText(g, n)}
                    {drawn < n && <span className="live-muted"> (newest {drawn} drawn)</span>}
                    {map && (
                      <>
                        {" "}
                        <button type="button" className="live-showme" onClick={() => requestShow(scope, g.key)} aria-label={`${shown === g.key ? "Hide from" : "Show on"} the map: ${countText(g, n)}`}>
                          {shown === g.key ? "Hide" : "Show me"}
                        </button>
                      </>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="live-muted">Positions as the vessels and aircraft broadcast them, refreshed every minute while this is on screen; ones with no transponder are not seen.</p>
        </aside>
      )}
    </div>
  );
}
