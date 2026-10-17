// The "Shadow fleet" layer of /live (off by default): one small dark-rimmed mark per vessel behaviour event (backend `maritime/`, migration 013),
// coloured by kind, plus a thin dashed track from each event's evidence points. Drawn over the other layers without changing them; the popup says
// what the event is and what it is not. Client-safe: imports only the shared file.

import { collection, pointFeature, type Feature } from "@/components/map/geo";
import type { LayerSpec } from "@/components/map/mapLayers";
import { evidenceLine, identityLine, kindLabel, KIND_COLOR, pct, SHADOW_COLOR, trackOf, type MaritimeEvent } from "@/lib/maritime-shared";

export const shadowId = (e: Pick<MaritimeEvent, "id">): string => `shadow:${e.id}`;

const SAYS = "Ohmega's own analysis of the ship positions it hears (AIS), not something a source reported. A pattern seen, not a finding of intent: a silence, an encounter, a rename and a long dwell all have innocent explanations.";

export function shadowLayers(events: MaritimeEvent[]): LayerSpec[] {
  const marks = events.filter((e) => e.lat !== null && e.lon !== null).map((e) =>
    pointFeature([e.lon as number, e.lat as number], {
      id: shadowId(e), col: KIND_COLOR[e.kind], r: 4 + Math.round(3 * e.confidence), title: e.summary, k: kindLabel(e.kind), conf: pct(e.confidence),
      who: identityLine(e), why: e.rationale, state: e.ended_at === null ? "ongoing" : "ended", ev: e.evidence.slice(-4).map(evidenceLine).join("\n"),
    }),
  );
  if (marks.length === 0) return [];
  const lines: Feature[] = events.flatMap((e) => {
    const t = trackOf(e);
    return t.length >= 2 ? [{ type: "Feature" as const, properties: { id: `shadowtrack:${e.id}` }, geometry: { type: "LineString" as const, coordinates: t } }] : [];
  });
  const specs: LayerSpec[] = [];
  if (lines.length > 0) specs.push({ group: "shadow-track", kind: "line", color: SHADOW_COLOR, data: collection(lines) });
  specs.push({
    group: "shadow", kind: "marks", color: SHADOW_COLOR, data: collection(marks),
    popup: (p) => ({
      kind: `${p.k} · Ohmega analysis`,
      title: String(p.title),
      when: `${p.state} · confidence ${p.conf}`,
      text: `${p.why}. ${SAYS}`,
      lines: [String(p.who), ...String(p.ev).split("\n").filter(Boolean)],
      source: "Ohmega, from AIS (full list at /intel/maritime)",
    }),
  });
  return specs;
}
