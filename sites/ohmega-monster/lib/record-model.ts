// The record: what named people and bodies said, from the statements ledger. Pure (no node imports), so
// server pages and client filters share it. Rows are written by the backend (`on_record.py`): on every daily
// section and brief as `on_record`, in the public ledger `record.json`, and in each theater dossier.
// A statement proves it was SAID, not that it is true; the pages say so once.

export type OnRecord = {
  id: string;
  speaker: string;
  role: string;
  affiliation: string;
  /** ISO alpha-2 of the affiliation when it is a country; "" for NATO, the UN, a company... */
  iso2: string;
  date: string;
  venue: string;
  /** Exact words (validated against the transcript at extraction), or "" when only a paraphrase exists. */
  quote: string;
  paraphrase: string;
  about: string[];
  about_iso2: string[];
  signal: string;
  /** -2 hostile .. +2 conciliatory, toward `about`. */
  stance: number;
  significance: string;
  url: string;
  /** The outlet that reported it, when the statement comes from a news report rather than the speaker's own text. */
  reported_by: string;
};

export type TonePoint = { date: string; stance: number; n: number };
export type ToneSeries = { affiliation: string; iso2: string; about: string; about_iso2: string; n: number; mean: number; points: TonePoint[] };
export type RecordLedger = { as_of: string; window_days: number; count: number; statements: OnRecord[]; tone: ToneSeries[] };

// ---- defensive coercion ---------------------------------------------------------------------
type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string => (typeof v === "string" ? v : typeof v === "number" ? String(v) : "");
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const strs = (v: unknown): string[] => arr(v).map(str).filter(Boolean);
const iso = (v: unknown): string => (/^[A-Za-z]{2}$/.test(str(v)) ? str(v).toUpperCase() : "");

/** Only http(s) links may be rendered as hrefs. */
function httpUrl(u: string): string {
  try {
    const p = new URL(u);
    return p.protocol === "http:" || p.protocol === "https:" ? p.href : "";
  } catch {
    return "";
  }
}

export function parseOnRecord(raw: unknown): OnRecord[] {
  return arr(raw)
    .filter(isObj)
    .map((r) => ({
      id: str(r.id),
      speaker: str(r.speaker),
      role: str(r.role),
      affiliation: str(r.affiliation),
      iso2: iso(r.iso2),
      date: str(r.date),
      venue: str(r.venue),
      quote: str(r.quote),
      paraphrase: str(r.paraphrase),
      about: strs(r.about),
      about_iso2: arr(r.about_iso2).map(iso).filter(Boolean),
      signal: str(r.signal) || "other",
      stance: Math.max(-2, Math.min(2, Math.round(num(r.stance) ?? 0))),
      significance: str(r.significance),
      url: httpUrl(str(r.url)),
      reported_by: str(r.reported_by),
    }))
    .filter((r) => r.id && r.speaker && (r.quote || r.paraphrase));
}

export function parseLedger(raw: unknown): RecordLedger | null {
  if (!isObj(raw)) return null;
  return {
    as_of: str(raw.as_of),
    window_days: num(raw.window_days) ?? 60,
    count: num(raw.count) ?? 0,
    statements: parseOnRecord(raw.statements),
    tone: arr(raw.tone)
      .filter(isObj)
      .map((t) => ({
        affiliation: str(t.affiliation),
        iso2: iso(t.iso2),
        about: str(t.about),
        about_iso2: iso(t.about_iso2),
        n: num(t.n) ?? 0,
        mean: num(t.mean) ?? 0,
        points: arr(t.points)
          .filter(isObj)
          .map((p) => ({ date: str(p.date), stance: num(p.stance), n: num(p.n) ?? 1 }))
          .filter((p): p is TonePoint => p.stance !== null && p.date !== "")
          .sort((a, b) => (a.date < b.date ? -1 : 1)),
      }))
      .filter((t) => t.affiliation && t.about && t.points.length > 1),
  };
}

// ---- presentation ---------------------------------------------------------------------------
export const SIGNAL_LABEL: Record<string, string> = {
  threat: "Threat",
  warning: "Warning",
  red_line: "Red line",
  commitment: "Commitment",
  offer: "Offer",
  demand: "Demand",
  reassurance: "Reassurance",
  accusation: "Accusation",
  denial: "Denial",
  policy_announcement: "Policy",
  tone_shift: "Tone shift",
  other: "Remark",
};
export const signalLabel = (s: string): string => SIGNAL_LABEL[s] ?? "Remark";

/** The stance scale in plain words, hostile to conciliatory. */
export const STANCE_LABEL: Record<number, string> = { [-2]: "hostile", [-1]: "critical", 0: "neutral", 1: "constructive", 2: "conciliatory" };
export const stanceLabel = (n: number): string => STANCE_LABEL[Math.round(n)] ?? "neutral";

/** "Vladimir Putin, President of Russia" -> speaker with their office. */
export const officeOf = (r: Pick<OnRecord, "role" | "affiliation">): string => [r.role, r.affiliation && !r.role.includes(r.affiliation) ? r.affiliation : ""].filter(Boolean).join(", ");

/** What they said: the exact words in quotation marks, else the paraphrase (marked as such by the caller). */
export const isQuote = (r: Pick<OnRecord, "quote">): boolean => r.quote.trim() !== "";

export const WINDOW_DAYS_DEFAULT = 60;

/** "2026-10-02" -> "2 Oct" (UTC); anything else passes through. */
export function dayLabel(d: string): string {
  const dt = new Date(`${d}T00:00:00Z`);
  return Number.isNaN(dt.getTime()) ? d : dt.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

export type RecordFilter = {
  speaker: string;
  /** Affiliation (the flag). */
  by: string;
  /** The counterpart the statement is about. */
  about: string;
  signal: string;
  from: string;
  to: string;
};
export const NO_FILTER: RecordFilter = { speaker: "", by: "", about: "", signal: "", from: "", to: "" };

export function applyFilter(rows: OnRecord[], f: RecordFilter): OnRecord[] {
  return rows.filter(
    (r) =>
      (!f.speaker || r.speaker === f.speaker) &&
      (!f.by || r.affiliation === f.by) &&
      (!f.about || r.about.includes(f.about)) &&
      (!f.signal || r.signal === f.signal) &&
      (!f.from || r.date >= f.from) &&
      (!f.to || r.date <= f.to),
  );
}

/** Distinct values with counts, most frequent first (ties alphabetical): the options of a filter. */
export function tally(values: string[]): { value: string; n: number }[] {
  const m = new Map<string, number>();
  for (const v of values) if (v) m.set(v, (m.get(v) ?? 0) + 1);
  return [...m.entries()].map(([value, n]) => ({ value, n })).sort((a, b) => b.n - a.n || a.value.localeCompare(b.value));
}

/** Newest first, ties kept in given order. */
export const newestFirst = (rows: OnRecord[]): OnRecord[] => rows.map((r, i) => ({ r, i })).sort((a, b) => (a.r.date < b.r.date ? 1 : a.r.date > b.r.date ? -1 : a.i - b.i)).map((x) => x.r);
