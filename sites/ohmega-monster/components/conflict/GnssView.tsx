"use client";

import { useEffect, useMemo, useState } from "react";

import IsoFlags from "@/components/IsoFlags";
import { sharePct, SEVERITY_LABEL, type GnssRow, type Provenance as ProvenanceData } from "@/lib/conflict-shared";
import { countryName } from "@/lib/flags";
import { loadLand } from "@/lib/globe/sphere";

import Provenance from "./Provenance";
import "./conflict.css";

// /intel/gnss: the day's GPS-interference zones as a flat map of cells (this page only: the live map never shows cells) over a table. Our own
// estimate and GPSJam's file are drawn differently (ours as filled squares, GPSJam's as rings) so agreement or disagreement is visible; colour
// is severity and nothing else. The coastline is the globe's detailed outline, fetched once; without it the zones still plot on a graticule.

type Region = { id: string; label: string; w: number; e: number; s: number; n: number };
const REGIONS: Region[] = [
  { id: "eu", label: "Europe and Middle East", w: -12, e: 78, s: 12, n: 72 },
  { id: "asia", label: "Asia", w: 60, e: 150, s: -8, n: 56 },
  { id: "world", label: "World", w: -180, e: 180, s: -60, n: 80 },
];

/** Land outlines as flat [lon, lat] runs, split where a line crosses the antimeridian. Input: the globe's unit-vector polylines. */
function lonLat(polys: Float32Array[]): number[][] {
  const out: number[][] = [];
  for (const p of polys) {
    let run: number[] = [];
    let prev = NaN;
    for (let i = 0; i + 2 < p.length; i += 3) {
      const lon = (Math.atan2(p[i + 1], p[i]) * 180) / Math.PI;
      const lat = (Math.asin(Math.max(-1, Math.min(1, p[i + 2]))) * 180) / Math.PI;
      if (!Number.isNaN(prev) && Math.abs(lon - prev) > 180) {
        if (run.length >= 4) out.push(run);
        run = [];
      }
      run.push(lon, lat);
      prev = lon;
    }
    if (run.length >= 4) out.push(run);
  }
  return out;
}

const path = (runs: number[][], r: Region): string =>
  runs
    .map((run) => {
      let d = "";
      let any = false;
      for (let i = 0; i < run.length; i += 2) {
        const inside = run[i] >= r.w - 10 && run[i] <= r.e + 10 && run[i + 1] >= r.s - 10 && run[i + 1] <= r.n + 10;
        if (!inside) { any = false; continue; }
        d += `${any ? "L" : "M"}${run[i].toFixed(2)} ${(-run[i + 1]).toFixed(2)}`;
        any = true;
      }
      return d;
    })
    .join("");

export default function GnssView({ day, zones, ours, theirs }: { day: string; zones: GnssRow[]; ours: ProvenanceData; theirs: ProvenanceData | null }) {
  const [region, setRegion] = useState("eu");
  const [coast, setCoast] = useState<number[][] | null>(null);
  const [source, setSource] = useState<"ohmega_adsb" | "gpsjam">("ohmega_adsb");
  const r = REGIONS.find((x) => x.id === region) ?? REGIONS[0];

  useEffect(() => {
    let dead = false;
    void loadLand().then((polys) => { if (!dead && polys) setCoast(lonLat(polys)); });
    return () => { dead = true; };
  }, []);

  const mine = useMemo(() => zones.filter((z) => z.source === "ohmega_adsb"), [zones]);
  const theirsRows = useMemo(() => zones.filter((z) => z.source === "gpsjam"), [zones]);
  const land = useMemo(() => (coast ? path(coast, r) : ""), [coast, r]);
  const rows = source === "ohmega_adsb" ? mine : theirsRows;
  const lonSpan = r.e - r.w;

  return (
    <div className="cx-view">
      <p className="cx-headline">
        <strong>{mine.length}</strong> {mine.length === 1 ? "zone" : "zones"} from our own estimate on {day} <Provenance p={ours} label="our interference zones" />
        {theirs && (
          <>
            {" · "}<strong>{theirsRows.length}</strong> from GPSJam <Provenance p={theirs} label="GPSJam's cells" />
          </>
        )}
      </p>

      <div className="cx-filters" role="group" aria-label="Map region">
        {REGIONS.map((x) => (
          <button key={x.id} type="button" className={`cx-pick${region === x.id ? " is-on" : ""}`} aria-pressed={region === x.id} onClick={() => setRegion(x.id)}>{x.label}</button>
        ))}
      </div>

      <svg className="cx-plot" viewBox={`${r.w} ${-r.n} ${lonSpan} ${r.n - r.s}`} preserveAspectRatio="xMidYMid meet" role="img"
        aria-label={`Map of GNSS interference zones on ${day}: ${mine.length} from Ohmega's estimate and ${theirsRows.length} from GPSJam`}>
        <rect x={r.w} y={-r.n} width={lonSpan} height={r.n - r.s} className="cx-sea" />
        {Array.from({ length: Math.floor(lonSpan / 10) + 1 }, (_, i) => Math.ceil(r.w / 10) * 10 + i * 10).filter((x) => x <= r.e).map((x) => (
          <line key={`x${x}`} x1={x} x2={x} y1={-r.n} y2={-r.s} className="cx-grat" vectorEffect="non-scaling-stroke" />
        ))}
        {Array.from({ length: Math.floor((r.n - r.s) / 10) + 1 }, (_, i) => Math.ceil(r.s / 10) * 10 + i * 10).filter((y) => y <= r.n).map((y) => (
          <line key={`y${y}`} x1={r.w} x2={r.e} y1={-y} y2={-y} className="cx-grat" vectorEffect="non-scaling-stroke" />
        ))}
        {land && <path d={land} className="cx-land" fill="none" vectorEffect="non-scaling-stroke" />}
        {mine.map((z) => (
          <rect key={z.id} x={z.lon - z.size_deg / 2} y={-(z.lat + z.size_deg / 2)} width={z.size_deg} height={z.size_deg} className={`cx-zone cx-sev-${z.severity}`}>
            <title>{`${countryName(z.country) || "Sea or border area"}: ${sharePct(z.degraded_share)} of ${z.aircraft} aircraft observations degraded (${z.severity})${z.flag ? `, ${z.flag}` : ""}`}</title>
          </rect>
        ))}
        {theirsRows.map((z) => (
          <circle key={z.id} cx={z.lon} cy={-z.lat} r={Math.max(0.35, lonSpan / 260)} className={`cx-ring cx-sev-${z.severity}`} vectorEffect="non-scaling-stroke">
            <title>{`GPSJam: ${sharePct(z.degraded_share)} of ${z.aircraft} aircraft degraded`}</title>
          </circle>
        ))}
      </svg>
      <ul className="cx-key" aria-label="Key">
        {(["low", "medium", "high"] as const).map((s) => (
          <li key={s}><span className={`cx-sw cx-sev-${s}`} aria-hidden="true" />{SEVERITY_LABEL[s]}</li>
        ))}
        <li><span className="cx-sw cx-sw-ours" aria-hidden="true" />Our estimate (one-degree cell)</li>
        <li><span className="cx-sw cx-sw-theirs" aria-hidden="true" />GPSJam cell</li>
      </ul>

      <div className="cx-filters" role="group" aria-label="Table source">
        <button type="button" className={`cx-pick${source === "ohmega_adsb" ? " is-on" : ""}`} aria-pressed={source === "ohmega_adsb"} onClick={() => setSource("ohmega_adsb")}>Our estimate ({mine.length})</button>
        {theirs && <button type="button" className={`cx-pick${source === "gpsjam" ? " is-on" : ""}`} aria-pressed={source === "gpsjam"} onClick={() => setSource("gpsjam")}>GPSJam ({theirsRows.length})</button>}
      </div>
      {rows.length === 0 ? (
        <p className="cx-empty">No zones in this source for {day}.</p>
      ) : (
        <div className="cx-scroll">
          <table className="cx-table">
            <thead>
              <tr>
                <th scope="col">Where</th>
                <th scope="col">Centre</th>
                <th scope="col">Severity</th>
                <th scope="col" title="Share of aircraft observations reporting poor navigation accuracy">Degraded</th>
                <th scope="col" title="Aircraft observations behind the share">Aircraft</th>
                {source === "ohmega_adsb" && <th scope="col" title="Against this cell's own history">Change</th>}
                {source === "ohmega_adsb" && theirs && <th scope="col" title="Does GPSJam's file show interference in the same cell">GPSJam</th>}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 120).map((z) => (
                <tr key={z.id}>
                  <td className="cx-place">{z.country ? <><IsoFlags codes={[z.country]} /> {countryName(z.country)}</> : <span className="cx-sub">sea or border area</span>}</td>
                  <td className="cx-date">{z.lat.toFixed(1)}, {z.lon.toFixed(1)}</td>
                  <td><span className={`cx-sevtag cx-sev-${z.severity}`}>{SEVERITY_LABEL[z.severity]}</span></td>
                  <td className="cx-num">{sharePct(z.degraded_share)}</td>
                  <td className="cx-num">{z.aircraft}</td>
                  {source === "ohmega_adsb" && <td>{z.flag === "new" ? "New zone" : z.flag === "intensifying" ? "Intensifying" : ""}</td>}
                  {source === "ohmega_adsb" && theirs && <td className="cx-sub">{z.cross_check === "agrees" ? "agrees" : z.cross_check === "not_in_gpsjam" ? "not in file" : ""}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
