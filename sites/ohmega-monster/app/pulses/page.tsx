import type { Metadata } from "next";

import PulseWall from "@/components/PulseWall";
import { fmtUtc, latestSnapshot, severitySorted } from "@/lib/intel";
import type { WallPulse } from "@/lib/pulse-wall";

export const metadata: Metadata = {
  title: "Pulses",
  description: "Every Pulse we track: one question, one 0–100 reading. Early readings — still calibrating.",
};

export default function PulsesPage() {
  const snap = latestSnapshot();
  // Flat and serialisable: the wall sorts and draws everything client-side.
  const pulses: WallPulse[] = severitySorted(snap).flatMap((s) =>
    s.pulses.map((p) => ({
      id: p.id,
      name: p.name,
      situation: s.title,
      question: p.question,
      low_end: p.low_end,
      high_end: p.high_end,
      position: p.position,
      band: p.band,
      confidence: p.confidence,
      last_assessed: p.last_assessed,
      history: p.history,
      rationale: p.rationale,
    })),
  );
  return (
    <div className="intel-page wall-page">
      <PulseWall pulses={pulses} asOf={snap?.built_at ?? ""} asOfLabel={snap?.built_at ? fmtUtc(snap.built_at) : "—"} />
    </div>
  );
}
