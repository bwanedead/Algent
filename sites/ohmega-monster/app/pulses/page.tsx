import type { Metadata } from "next";
import Link from "next/link";

import PulseBoard, { situationAnchor } from "@/components/IntelPulseBoard";
import { SpectrumLegend } from "@/components/PulseSpectrum";
import { BAND_LABEL, fmtUtc, latestSnapshot, maxBand, severitySorted, type Band } from "@/lib/intel";

export const metadata: Metadata = {
  title: "Pulses",
  description: "Every Pulse we track: one question, one 0–100 reading, with the reasoning behind it. Early readings — still calibrating.",
};

const BAND_RANGES: { band: Band; range: string }[] = [
  { band: "calm", range: "0–25" },
  { band: "elevated", range: "25–50" },
  { band: "severe", range: "50–75" },
  { band: "critical", range: "75–100" },
];

export default function PulsesPage() {
  const snap = latestSnapshot();
  const situations = severitySorted(snap);
  const pulses = situations.flatMap((s) => s.pulses);
  const assessed = pulses.filter((p) => p.position !== null).length;

  return (
    <div className="intel-page">
      <div className="intel-strip" role="group" aria-label="Status">
        <span className="intel-strip-title">Pulses</span>
        <span className="intel-strip-item">
          <span className="intel-micro">As of</span> {snap?.built_at ? fmtUtc(snap.built_at) : "—"}
        </span>
        <span className="intel-strip-item">
          <b className="intel-num-sm">{situations.length}</b> <span className="intel-micro">Situations</span>
        </span>
        <span className="intel-strip-item">
          <b className="intel-num-sm">{assessed}</b>
          <span className="intel-micro">/{pulses.length} assessed</span>
        </span>
        <span className="intel-trust" title="Pulses are new. Treat every reading as provisional.">
          Early readings — still calibrating
        </span>
      </div>

      <section className="pulses-intro" aria-label="About Pulses">
        <p className="intel-text">
          A Pulse is one question about the world, answered with a single number from 0 to 100. Zero means calm, a hundred means as bad as it gets, and each Pulse spells out
          what both ends look like. Open any Pulse to see its question, how it has moved and why we read it the way we do. These are early readings — we are still
          calibrating them, so treat every number as provisional.
        </p>
        <SpectrumLegend />
      </section>

      {!snap || situations.length === 0 ? (
        <p className="intel-empty">No Pulses have been published yet. Check back soon.</p>
      ) : (
        <>
          <nav className="pulses-bar" aria-label="Jump to a Situation">
            <span className="pulses-bar-band" aria-label="Severity bands">
              {BAND_RANGES.map((b) => (
                <span key={b.band} className={`intel-chip intel-band-${b.band}`} title={`${BAND_LABEL[b.band]}: ${b.range}`}>
                  {BAND_LABEL[b.band]} <span className="pulses-bar-range">{b.range}</span>
                </span>
              ))}
            </span>
            <span className="pulses-bar-jump">
              <span className="intel-micro">Jump to</span>
              {situations.map((s) => (
                <a key={s.id} href={`#${situationAnchor(s.id)}`} className={`intel-chip intel-band-${maxBand(s.pulses)}`} title="Colour is the most severe Pulse in this Situation">
                  {s.title}
                </a>
              ))}
            </span>
          </nav>

          <PulseBoard situations={situations} />
        </>
      )}

      <p className="intel-note daily-xlink">
        <Link href="/intel">Intelligence board — Theaters, Briefs and the track record →</Link>
        {" · "}
        <Link href="/geopolitics">Geopolitics — the daily report →</Link>
      </p>
    </div>
  );
}
