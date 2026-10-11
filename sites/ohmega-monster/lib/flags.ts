/**
 * Country flags for the feed/article chrome.
 *
 * Pipeline stores regional-indicator emoji (🇦🇺). On many Windows / Linux font stacks those
 * collapse to the two letter glyphs "A""U" instead of a flag image — so we render PNG flags
 * from the ISO code, with the emoji kept only as a last-resort text fallback.
 */

const RI_A = 0x1f1e6; // regional indicator symbol letter A

/** Regional-indicator pair (🇦🇺) -> ISO-3166 alpha-2 ("AU"), or null. */
export function flagEmojiToIso(flag: string): string | null {
  const cps = [...flag];
  if (cps.length !== 2) return null;
  const a = cps[0].codePointAt(0);
  const b = cps[1].codePointAt(0);
  if (a == null || b == null) return null;
  const aa = a - RI_A;
  const bb = b - RI_A;
  if (aa < 0 || aa > 25 || bb < 0 || bb > 25) return null;
  return String.fromCharCode(65 + aa, 65 + bb);
}

/** ISO-3166 alpha-2 -> regional-indicator pair (the shape FlagRow takes). */
export function isoToFlagEmoji(iso2: string): string {
  return [...iso2.toUpperCase()].map((c) => String.fromCodePoint(RI_A + c.charCodeAt(0) - 65)).join("");
}

/** Small flag image URL (flagcdn — static PNGs, no JS). EU is supported. */
export function flagImageUrl(iso2: string, width = 20): string {
  const w = width <= 20 ? 20 : width <= 40 ? 40 : 80;
  return `https://flagcdn.com/w${w}/${iso2.toLowerCase()}.png`;
}

/** Names the Intl region table gets wrong for a news site, or lacks (older ICU builds). */
const NAME_OVERRIDES: Record<string, string> = {
  XK: "Kosovo",
  TW: "Taiwan",
  PS: "Palestine",
  HK: "Hong Kong",
  MO: "Macau",
  GB: "United Kingdom",
  US: "United States",
  RU: "Russia",
  KR: "South Korea",
  KP: "North Korea",
  IR: "Iran",
  SY: "Syria",
  VN: "Vietnam",
  CZ: "Czechia",
  TR: "Turkey",
  EU: "European Union",
};

let regionNames: Intl.DisplayNames | null | undefined;

/** ISO-3166 alpha-2 -> English country/region name ("SA" -> "Saudi Arabia"); the code itself when unknown. */
export function countryName(iso2: string): string {
  const code = iso2.trim().toUpperCase();
  if (NAME_OVERRIDES[code]) return NAME_OVERRIDES[code];
  if (regionNames === undefined) {
    try {
      regionNames = new Intl.DisplayNames("en", { type: "region" });
    } catch {
      regionNames = null;
    }
  }
  try {
    const name = regionNames?.of(code);
    if (name && name !== code) return name;
  } catch {
    // not a region code
  }
  return code;
}
