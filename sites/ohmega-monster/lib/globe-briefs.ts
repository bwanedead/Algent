import { allDailyDates, daily, type Daily } from "./daily";
import { textLinker } from "./entities";
import { dailyMentions } from "./globe-mentions";
import type { CountryBrief } from "./globe/data";

// A country's full brief history for the globe panel: every daily section and development that names it, newest first. Which items
// count and what theme each reads as come from lib/globe-mentions.ts, the same walker that colours the map. Server only.

const DOMAIN = "geopolitics";

export async function countryBriefs(iso: string): Promise<CountryBrief[]> {
  const [dates, linker] = await Promise.all([allDailyDates(DOMAIN), textLinker()]); // dates are newest first; each daily is a cached read
  const dailies = (await Promise.all(dates.map((d) => daily(DOMAIN, d)))).filter((d): d is Daily => d !== null);
  const out: CountryBrief[] = [];
  for (const d of dailies) {
    const seen = new Set<string>();
    for (const m of dailyMentions(d, dates, linker)) {
      if (!m.text || !m.isos.includes(iso) || seen.has(m.text)) continue;
      seen.add(m.text);
      out.push({ theme: m.theme, date: m.date, text: m.text, href: m.href, kind: m.kind });
    }
  }
  return out;
}
