// Pure presentation helpers for Pulses. No node imports: safe in client components.
import type { Band } from "./intel";

export const BAND_LABEL: Record<Band, string> = { calm: "Calm", elevated: "Elevated", severe: "Severe", critical: "Critical", unassessed: "Not yet assessed" };

/** Band for a 0-100 reading (calm 0-25, elevated 25-50, severe 50-75, critical 75-100). */
export function bandAt(position: number | null): Band {
  if (position === null) return "unassessed";
  return position >= 75 ? "critical" : position >= 50 ? "severe" : position >= 25 ? "elevated" : "calm";
}

/** "▲ +3" / "▼ −2" / "◆ 0" / "—" for a Pulse change. */
export function fmtDelta(v: number | null): string {
  if (v === null) return "—";
  const r = Math.round(v * 10) / 10;
  if (r === 0) return "◆ 0";
  return `${r > 0 ? "▲ +" : "▼ −"}${Math.abs(r)}`;
}
export const deltaClass = (v: number | null) => (v === null || Math.round(v * 10) === 0 ? "flat" : v > 0 ? "up" : "down");
