import { BAND_LABEL, bandAt } from "@/lib/band";
import type { Band } from "@/lib/intel";

// The 0-100 spectrum behind every Pulse number: four muted band segments, a marker at the reading.
// Pure server component; colours come from the intel-band-* classes so both displays work.

const SEGMENTS: Band[] = ["calm", "elevated", "severe", "critical"];
const TICKS = [0, 25, 50, 75, 100];

/** One line, shown once per page above the first Pulses. */
export function SpectrumLegend() {
  return (
    <p className="pulse-legend">
      <span className="pulse-legend-scale" aria-hidden="true">
        {SEGMENTS.map((b) => (
          <span key={b} className={`intel-band-${b}`} />
        ))}
      </span>
      <span>0 = calm · 100 = extreme</span>
      <span className="intel-micro">calm 0–25 · elevated 25–50 · severe 50–75 · critical 75–100</span>
    </p>
  );
}

export default function PulseSpectrum({ position, variant = "compact" }: { position: number | null; variant?: "compact" | "full" }) {
  const full = variant === "full";
  if (position === null) {
    return (
      <span className={`pulse-spec pulse-spec-${variant} pulse-spec-empty`} role="img" aria-label="Not yet assessed">
        <span className="pulse-spec-track" />
        <span className="pulse-spec-none">Not yet assessed</span>
      </span>
    );
  }
  const pos = Math.min(100, Math.max(0, position));
  const active = bandAt(pos);
  const edge = pos <= 8 ? " pulse-spec-lo" : pos >= 92 ? " pulse-spec-hi" : "";
  return (
    <span className={`pulse-spec pulse-spec-${variant} intel-band-${active}`} role="img" aria-label={`${Math.round(pos)} out of 100, ${BAND_LABEL[active].toLowerCase()}`}>
      <span className="pulse-spec-track">
        {SEGMENTS.map((b) => (
          <span key={b} className={`pulse-spec-seg intel-band-${b}${b === active ? " is-on" : ""}`} />
        ))}
        <span className={`pulse-spec-mark${edge}`} style={{ left: `${pos}%` }}>
          {full && <span className="pulse-spec-val">{Math.round(pos)}</span>}
        </span>
      </span>
      {full && (
        <span className="pulse-spec-ticks" aria-hidden="true">
          {TICKS.map((t) => (
            <span key={t} style={{ left: `${t}%` }} className={t === 0 ? "t-first" : t === 100 ? "t-last" : undefined}>
              {t}
            </span>
          ))}
        </span>
      )}
    </span>
  );
}
