import { confidenceWord, durationText, evidenceLine, identityLine, kindLabel, KIND_COLOR, KIND_MEANING, pct, trackOf, type MaritimeEvent } from "@/lib/maritime-shared";

import MiniTrack from "./MiniTrack";

import "./maritime.css";

// One behaviour event in full: what was seen, why it was flagged (with the numbers), the vessel's identity, a mini track and the evidence points.
// Shared by the /live card, the /intel/maritime row and the vessel place page. No state and no server imports: usable from both kinds of component.

export default function EventDetail({ e, nowMs }: { e: MaritimeEvent; nowMs: number | null }) {
  const dur = nowMs !== null ? durationText(e.started_at, e.ended_at, nowMs) : "";
  const track = trackOf(e);
  return (
    <div className="mb-detail">
      <p className="mb-kind" style={{ color: KIND_COLOR[e.kind] }}>
        {kindLabel(e.kind)} <span className="mb-muted">· {e.ended_at === null ? "ongoing" : e.state === "unresolved" ? "never heard again" : "ended"}{dur ? ` · ${dur}` : ""}</span>
      </p>
      <p className="mb-summary">{e.summary}</p>
      <p className="mb-why">
        <span className="mb-label">Why flagged</span> {e.rationale}
      </p>
      <p className="mb-id">{identityLine(e)}{e.mmsi2 ? ` — with ${[e.name2 || `MMSI ${e.mmsi2}`, `MMSI ${e.mmsi2}`, e.flag2 ? `flag ${e.flag2}` : ""].filter(Boolean).join(" · ")}` : ""}</p>
      <div className="mb-row">
        {track.length > 0 && <MiniTrack points={track} color={KIND_COLOR[e.kind]} label={`Track of the evidence points for ${e.summary}`} />}
        <ul className="mb-evidence" aria-label="Evidence points">
          {e.evidence.slice(-8).map((p, i) => (
            <li key={i}>{evidenceLine(p)}</li>
          ))}
        </ul>
      </div>
      <p className="mb-muted mb-foot">
        Confidence {pct(e.confidence)} ({confidenceWord(e.confidence)}). Ohmega analysis of AIS, not something a source reported: {KIND_MEANING[e.kind]}. A pattern seen, not a finding of intent.
      </p>
    </div>
  );
}
