import type { Metadata } from "next";

import PulseWall from "@/components/PulseWall";
import { fmtUtc, latestSnapshot, severitySorted } from "@/lib/intel";
import { toWallPulse, type WallPulse } from "@/lib/pulse-wall";

export const metadata: Metadata = {
  title: "Pulses",
  description: "Every Pulse we track: one question, one 0–100 reading. Early readings — still calibrating.",
};

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function PulsesPage() {
  const snap = await latestSnapshot();
  // Flat and serialisable: the wall sorts and draws everything client-side.
  const pulses: WallPulse[] = severitySorted(snap).flatMap((s) => s.pulses.map((p) => toWallPulse(p, s.title)));
  return (
    <div className="intel-page wall-page">
      <PulseWall pulses={pulses} asOf={snap?.built_at ?? ""} asOfLabel={snap?.built_at ? fmtUtc(snap.built_at) : "—"} />
    </div>
  );
}
