import { liveEvents, liveTouching } from "@/lib/live";

import "@/app/live/live.css";

import LiveNowStrip from "./LiveNowStrip";

// Server component of the live surfaces: the "Live now" strip that theater sections and dossiers show when a live event touches their
// countries. The matching is done here (lib/live-shared `liveTouching`); the strip itself is a client component (LiveNowStrip) so
// each event can be shown on the theater's map. `scope` names the theater so the strip and its map find each other (theaterLive.ts).

/** "Live now": renders nothing unless a current live event touches a country the text names. */
export async function LiveNow({ text, scope }: { text: string; scope: string }) {
  const touching = liveTouching(await liveEvents(), text);
  if (touching.length === 0) return null;
  return <LiveNowStrip events={touching} scope={scope} />;
}
