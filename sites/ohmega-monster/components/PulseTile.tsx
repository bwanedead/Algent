// THE Pulse, everywhere: one uniform tile (name, number, band meter, optional change) that opens the
// same popover (PulseDetail). Same shape, same scale, so the eye learns it once.
// Lay tiles out in a `.pt-grid` (components/pulse-tile.css) or any grid of your own.

import { BAND_LABEL, deltaClass, fmtDelta } from "@/lib/band";
import type { WallPulse } from "@/lib/pulse-wall";

import IsoFlags from "./IsoFlags";
import PulseDetail from "./PulseDetail";
import Popover from "./Popover";
import "./pulse-tile.css";

const clamp = (v: number) => Math.min(100, Math.max(0, v));

/** Slim 0-100 meter; a ghost tick marks where the reading was at the start of the period. */
function Meter({ position, from }: { position: number | null; from: number | null }) {
  if (position === null) return <span className="pt-meter pt-meter-empty" aria-hidden="true" />;
  return (
    <span className="pt-meter" aria-hidden="true">
      <span className="pt-fill" style={{ width: `${clamp(position)}%` }} />
      {from !== null && <span className="pt-ghost" style={{ left: `${clamp(from)}%` }} />}
      <span className="pt-mark" style={{ left: `${clamp(position)}%` }} />
    </span>
  );
}

export default function PulseTile({
  pulse,
  delta,
  period,
  size = "m",
  note,
  showDelta = true,
  anchor = true,
}: {
  pulse: WallPulse;
  /** Change over `period`. Given: the meter gets a ghost marker and the popover shows it. null: no baseline. */
  delta?: number | null;
  period?: string;
  size?: "s" | "m";
  /** A tiny extra line, e.g. "in this report: 71". */
  note?: string;
  /** false: keep the ghost marker and popover change but leave the ▲/▼ off the tile face. */
  showDelta?: boolean;
  /** false: no id="pulse-<id>" (and no #pulse-<id> deep link), for pages that show one Pulse twice. */
  anchor?: boolean;
}) {
  const pos = pulse.position === null ? null : Math.round(pulse.position);
  const from = pulse.position !== null && delta !== undefined && delta !== null ? pulse.position - delta : null;
  const trigger = (
    <>
      <span className="pt-name">
        <IsoFlags codes={pulse.actors_iso2} />
        {pulse.title}
      </span>
      <span className="pt-row">
        <span className={pos === null ? "pt-num pt-num-none" : "pt-num"}>{pos === null ? "—" : pos}</span>
        {showDelta && delta !== undefined && <span className={`pt-delta pt-delta-${deltaClass(delta)}`}>{fmtDelta(delta)}</span>}
      </span>
      <Meter position={pulse.position} from={from} />
      {note && <span className="pt-note">{note}</span>}
      <span className="intel-sr">{pos === null ? ": not yet assessed" : `: ${pos} out of 100, ${BAND_LABEL[pulse.band].toLowerCase()}`}</span>
    </>
  );
  return (
    <Popover label={pulse.title} trigger={trigger} triggerClassName={`pt pt-${size} intel-band-${pulse.band}`} id={anchor ? `pulse-${pulse.id}` : undefined}>
      <PulseDetail pulse={pulse} delta={delta} period={period} />
    </Popover>
  );
}
