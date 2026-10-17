import { dbRows } from "@/lib/store";

import { addDaysIso, type SanctionsRow } from "./sanctions-shared";

export * from "./sanctions-shared";

const SOURCES = new Set(["ofac", "uk", "eu"]);
const valid = (r: SanctionsRow): boolean => SOURCES.has(r.source) && (r.action === "designated" || r.action === "delisted") && /^\d{4}-\d{2}-\d{2}$/.test(r.on_date);

const today = (): string => new Date().toISOString().slice(0, 10);

/** Designations and delistings of the last `days` days, newest first; [] without a database. */
export async function recentSanctions(days = 90, limit = 1500): Promise<SanctionsRow[]> {
  const rows = await dbRows<SanctionsRow>("sanctions_events", `select=*&on_date=gte.${addDaysIso(today(), -days)}&order=on_date.desc,observed_on.desc&limit=${limit}`);
  return rows.filter(valid);
}

/** Recent events that name one country (an actor page), newest first. */
export async function sanctionsForCountry(iso: string, days = 180, limit = 200): Promise<SanctionsRow[]> {
  if (!/^[A-Za-z]{2}$/.test(iso)) return [];
  const rows = await dbRows<SanctionsRow>(
    "sanctions_events",
    `select=*&countries=cs.{${iso.toUpperCase()}}&on_date=gte.${addDaysIso(today(), -days)}&order=on_date.desc&limit=${limit}`,
  );
  return rows.filter(valid);
}
