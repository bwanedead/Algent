import { claimOf } from "./daily";
import { countryName } from "./flags";
import type { GlobeData } from "./globe/data";
import { hudView } from "./views";

// The /globe page's per-country channel data: when each state was last named, what about, the theaters it is tied to and the newest headline that names it.
// The worker server builds it (backend `views/hud.py`, the `globe` block of the HUD view: the theme rule in `views/themes.py` is documented in
// lib/globe/themes.ts) from what is already published (no model calls, no new documents); this module reads that one view and words the headlines.
// Server only (reads a document).

const HEADLINE_MAX = 150;

export async function globeData(): Promise<GlobeData | null> {
  const globe = (await hudView())?.globe;
  if (!globe) return null;
  const countries = Object.fromEntries(
    Object.entries(globe.countries).map(([iso, c]) => [iso, { ...c, name: c.name || countryName(iso), headline: c.headline ? { ...c.headline, text: claimOf(c.headline.text, HEADLINE_MAX) } : null }]),
  );
  return { ...globe, countries };
}
