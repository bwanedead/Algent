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

/** Small flag image URL (flagcdn — static PNGs, no JS). EU is supported. */
export function flagImageUrl(iso2: string, width = 20): string {
  const w = width <= 20 ? 20 : width <= 40 ? 40 : 80;
  return `https://flagcdn.com/w${w}/${iso2.toLowerCase()}.png`;
}
