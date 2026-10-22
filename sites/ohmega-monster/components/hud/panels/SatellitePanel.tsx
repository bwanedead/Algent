"use client";

import Link from "next/link";
import { useMemo } from "react";

import { useSatellite } from "@/components/satellite/useSatellite";
import { bySignal, CHANGE_WORD, NIGHT_WORD, provText } from "@/lib/satellite-shared";

import type { PanelProps } from "../types";

const TOP = 6;

/** The watched places that moved most: the machine change signal and the night-light verdict, each with an info hover saying how it was made and how much
 *  of our own history it rests on. The same document as /intel/satellite; the pictures are there. */
export default function SatellitePanel(_props: PanelProps) {
  const { doc, status } = useSatellite(true);
  const rows = useMemo(() => (doc ? doc.sites.filter((s) => s.latest && s.change).sort(bySignal).slice(0, TOP) : []), [doc]);
  if (!doc) return <p className="hud-none">{status === "none" ? "No satellite imagery has been published yet." : "Loading satellite watch..."}</p>;
  return (
    <>
      <p className="hud-cap">Most changed · Sentinel-2, our own score</p>
      {rows.length > 0 ? (
        <ul className="hud-rows hud-table">
          {rows.map((s) => {
            const c = s.change;
            const flag = c?.label === "changed" ? "above" : s.night?.label === "dimmer" ? "below" : null;
            return (
              <li key={s.id}>
                <Link href={`/intel/satellite#${s.id}`} className="hud-row">
                  {flag ? <span className={`hud-flag hud-flag-${flag}`}>{flag === "above" ? "▲ changed" : "▼ dimmer"}</span> : null}
                  <span className="hud-row-text">{s.name}</span>
                  <span className="hud-k" title={c ? provText(c) : undefined}>{c && c.score !== null ? c.score.toFixed(3) : CHANGE_WORD[c?.label ?? "learning"]}</span>
                </Link>
                {s.night && s.night.label !== "steady" && s.night.label !== "learning" ? (
                  <span className="hud-k" title={provText(s.night)}>{`Night light ${NIGHT_WORD[s.night.label].toLowerCase()}`}</span>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : <p className="hud-none">No watched place has a before and after pair yet.</p>}
      <p className="hud-foot">
        {doc.counts.with_imagery} of {doc.counts.watched} watched places have imagery, as of {doc.as_of.slice(0, 10)}. A score is a machine signal that two pictures differ, never what
        changed; a place with few earlier looks is still learning and is not flagged. Hover a score for how it was made.
      </p>
    </>
  );
}
