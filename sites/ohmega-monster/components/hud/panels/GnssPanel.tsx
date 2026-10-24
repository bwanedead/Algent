"use client";

import Link from "next/link";

import Stat from "@/components/stats/Stat";
import { sharePct, SEVERITY_LABEL } from "@/lib/conflict-shared";
import { shortDate } from "@/lib/calendar-shared";

import { pointsAt, type PanelProps } from "../types";

/** The strongest GPS-interference zones of the newest day (Ohmega's own ADS-B estimate). Colour is severity; the "i" gives basis, limits and since when. */
export default function GnssPanel({ ctx }: PanelProps) {
  const g = ctx.data.gnss;
  if (!g) return <p className="hud-none">No interference zones published yet.</p>;
  return (
    <>
      <p className="hud-sub">
        <span className="cx-hud-n"><Stat id="gnss_zones" value={g.total} /></span> zones on {shortDate(g.day)}
      </p>
      <ul className="hud-rows hud-table">
        {g.zones.map((z) => (
          <li key={z.id} {...pointsAt(ctx, z.iso)}>
            <span className="hud-row">
              <span className={`cx-sevtag cx-sev-${z.severity}`} title={`${SEVERITY_LABEL[z.severity]} interference`}>{sharePct(z.share)}</span>
              <span className="hud-row-text">{z.where}</span>
              {z.flag && <span className="hud-k">{z.flag === "new" ? "new" : "intensifying"}</span>}
            </span>
          </li>
        ))}
      </ul>
      <p className="hud-foot"><Link href="/intel/gnss">All zones and the map</Link></p>
    </>
  );
}
