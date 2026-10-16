import { countryName } from "./flags";

// Country names as they appear in running text: the registry that lets prose link "Iran" or "Russian forces" to the
// state's actor page. Pure (no I/O): the names come from flags.ts (the one ISO name map), plus the short forms and
// demonyms a news site actually writes. Matching is exact-case and on word boundaries, longest name first, so
// "South Korea" never reads as "Korea" and "us" the pronoun is never "US".

/** Short forms and alternate names (the ISO name map has the formal one). */
const EXTRA: Record<string, string[]> = {
  US: ["USA", "U.S.", "America"],
  GB: ["UK", "Britain", "Great Britain"],
  AE: ["UAE"],
  CD: ["DR Congo", "DRC", "Democratic Republic of the Congo"],
  CG: ["Republic of the Congo"],
  CI: ["Ivory Coast"],
  MM: ["Burma"],
  TR: ["Türkiye", "Turkiye"],
  KR: ["S. Korea"],
  KP: ["N. Korea"],
};

/** Demonyms (a plural `s` is added by the builder where it reads). */
const DEMONYMS: Record<string, string[]> = {
  US: ["American"], GB: ["British"], RU: ["Russian"], UA: ["Ukrainian"], CN: ["Chinese"], IR: ["Iranian"], IL: ["Israeli"],
  SA: ["Saudi"], TR: ["Turkish"], IN: ["Indian"], PK: ["Pakistani"], JP: ["Japanese"], KR: ["South Korean"], KP: ["North Korean"],
  TW: ["Taiwanese"], DE: ["German"], FR: ["French"], IT: ["Italian"], ES: ["Spanish"], PL: ["Polish"], SY: ["Syrian"],
  IQ: ["Iraqi"], LB: ["Lebanese"], YE: ["Yemeni"], EG: ["Egyptian"], SD: ["Sudanese"], ET: ["Ethiopian"], ER: ["Eritrean"],
  SO: ["Somali"], LY: ["Libyan"], DZ: ["Algerian"], MA: ["Moroccan"], TN: ["Tunisian"], NG: ["Nigerian"], ZA: ["South African"],
  CD: ["Congolese"], AF: ["Afghan"], MM: ["Burmese"], TH: ["Thai"], VN: ["Vietnamese"], PH: ["Filipino"], ID: ["Indonesian"],
  AU: ["Australian"], CA: ["Canadian"], MX: ["Mexican"], BR: ["Brazilian"], AR: ["Argentine"], VE: ["Venezuelan"],
  CO: ["Colombian"], CU: ["Cuban"], QA: ["Qatari"], AE: ["Emirati"], KW: ["Kuwaiti"], OM: ["Omani"], JO: ["Jordanian"],
  PS: ["Palestinian"], AM: ["Armenian"], AZ: ["Azerbaijani"], GE: ["Georgian"], BY: ["Belarusian"], KZ: ["Kazakh"],
  UZ: ["Uzbek"], RS: ["Serbian"], GR: ["Greek"], NL: ["Dutch"], SE: ["Swedish"], NO: ["Norwegian"], FI: ["Finnish"],
  DK: ["Danish"], BE: ["Belgian"], CH: ["Swiss"], AT: ["Austrian"], HU: ["Hungarian"], RO: ["Romanian"], BG: ["Bulgarian"],
  CZ: ["Czech"], SK: ["Slovak"], LT: ["Lithuanian"], LV: ["Latvian"], EE: ["Estonian"], MD: ["Moldovan"], KE: ["Kenyan"],
  GH: ["Ghanaian"], ML: ["Malian"],
};

/** Names that are also ordinary words or given names: never linked on their own. */
const AMBIGUOUS = new Set(["Jordan", "Chad"]);

const IRREGULAR = /\(|\s-\s|SAR/; // "Congo - Kinshasa", "Myanmar (Burma)": not how prose writes them
const NO_PLURAL = /(?:ese|ish|ss|s|ch|ee)$/;

/** Every written form of one state's name. */
export function aliasesFor(iso: string): string[] {
  const name = countryName(iso);
  const out = new Set<string>();
  if (name !== iso && !IRREGULAR.test(name)) out.add(name);
  for (const x of EXTRA[iso] ?? []) out.add(x);
  for (const d of DEMONYMS[iso] ?? []) {
    out.add(d);
    if (!NO_PLURAL.test(d)) out.add(`${d}s`);
  }
  if (iso === "EU") out.add("EU");
  return Array.from(out).filter((a) => !AMBIGUOUS.has(a));
}

export type Linker = { re: RegExp; iso: ReadonlyMap<string, string> };

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** A matcher for the given states (those that have a page to land on); null when there are none. */
export function buildLinker(isos: Iterable<string>): Linker | null {
  const iso = new Map<string, string>();
  for (const code of Array.from(isos)) for (const a of aliasesFor(code)) if (!iso.has(a)) iso.set(a, code);
  if (iso.size === 0) return null;
  const forms = Array.from(iso.keys()).sort((a, b) => b.length - a.length).map(escape);
  // Word edges that also hold for "U.S." and "Türkiye"; "Indian Ocean" is not India.
  const re = new RegExp(`(?<![\\p{L}\\p{N}_])(?:${forms.join("|")})(?![\\p{L}\\p{N}_])(?!\\s+Ocean)`, "gu");
  return { re, iso };
}

export type Segment = { text: string; iso?: string };

/** The text cut into plain runs and country mentions. Only the FIRST mention of each state is marked (a paragraph full of
 *  links is noise); `skip` is a state to leave alone (the page is already about it). */
export function linkText(text: string, linker: Linker | null, skip = ""): Segment[] {
  if (!linker || !text) return [{ text }];
  const seen = new Set<string>(skip ? [skip] : []);
  const out: Segment[] = [];
  let at = 0;
  for (const m of Array.from(text.matchAll(linker.re))) {
    const code = linker.iso.get(m[0]);
    if (!code || seen.has(code)) continue;
    seen.add(code);
    const i = m.index ?? 0;
    if (i > at) out.push({ text: text.slice(at, i) });
    out.push({ text: m[0], iso: code });
    at = i + m[0].length;
  }
  if (at < text.length) out.push({ text: text.slice(at) });
  return out.length > 0 ? out : [{ text }];
}

/** The state a whole name stands for ("Russia", "Russian"), or null. For node labels and actor lists, not prose. */
export const isoForName = (name: string, linker: Linker | null): string | null => linker?.iso.get(name.trim()) ?? null;
