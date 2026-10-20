"use client";

import Tip from "@/components/Tip";
import { BASIS_LABEL, provenanceText, type Provenance as ProvenanceData } from "@/lib/conflict-shared";

import "./conflict.css";

/** What kind of figure this is, next to it: the basis in words and an "i" whose hover gives the coverage limit and, for our own counts, since when. */
export default function Provenance({ p, label }: { p: ProvenanceData; label: string }) {
  return (
    <span className="cx-prov">
      <span className="cx-basis">{BASIS_LABEL[p.basis]}</span>
      <Tip corner label={label} text={provenanceText(p)} />
    </span>
  );
}
