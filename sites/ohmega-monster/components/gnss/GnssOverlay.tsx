"use client";

// The globe's "Interference" mode in one element: loads the document, draws the canvas and the small legend. It draws nothing when `active` is false
// and fetches nothing until it is first switched on. The legend states what kind of figure this is (our estimate, a minimum, since when) and
// lets the reader hide either source.

import { useMemo, useState, type MutableRefObject } from "react";

import Tip from "@/components/Tip";
import { provenanceText } from "@/lib/conflict-shared";

import GnssLayer from "./GnssLayer";
import { useGnss } from "./useGnss";

import "./gnss.css";

export default function GnssOverlay({ active, matrix, cam }: { active: boolean; matrix: MutableRefObject<number[]>; cam: MutableRefObject<{ zoom: number }> }) {
  const { doc, status } = useGnss(active);
  const [ours, setOurs] = useState(true);
  const [gpsjam, setGpsjam] = useState(true);
  const on = useMemo(() => ({ ours, gpsjam }), [ours, gpsjam]);
  if (!active) return null;
  if (!doc) return <p className="gj-status" role="status">{status === "none" ? "No interference data has been published yet." : "Loading interference zones..."}</p>;
  const nOurs = doc.zones.filter((z) => z.src === "o").length;
  const nTheirs = doc.zones.length - nOurs;
  return (
    <>
      <GnssLayer zones={doc.zones} on={on} matrix={matrix} cam={cam} />
      <div className="gj-panel">
        <p className="gj-head">GPS interference <i>{doc.date}</i></p>
        <ul>
          <li>
            <button type="button" className={ours ? "is-on" : ""} aria-pressed={ours} onClick={() => setOurs((v) => !v)}>
              <span className="gj-sw" aria-hidden="true" /> <span className="gj-name">Our estimate</span> <span className="gj-val">{nOurs}</span>
            </button>
            <Tip corner label="our interference estimate" text={provenanceText({ basis: "our_estimate", coverage_note: doc.p.ours.coverage_note, baseline_since: doc.p.ours.baseline_since ?? null })} />
          </li>
          <li>
            <button type="button" className={gpsjam ? "is-on" : ""} aria-pressed={gpsjam} onClick={() => setGpsjam((v) => !v)}>
              <span className="gj-sw gj-sw-ring" aria-hidden="true" /> <span className="gj-name">GPSJam (strong cells)</span> <span className="gj-val">{nTheirs}</span>
            </button>
            <Tip corner label="GPSJam's cells" text={provenanceText({ basis: "third_party", coverage_note: doc.p.gpsjam.coverage_note, baseline_since: null })} />
          </li>
        </ul>
        <p className="gj-note">Colour is severity: amber low, orange medium, red high. A ring inside a glow marks a new or intensifying zone. Where aircraft report poor navigation accuracy; not proof of who is jamming.</p>
      </div>
    </>
  );
}
