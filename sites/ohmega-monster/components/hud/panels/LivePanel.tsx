"use client";

import Link from "next/link";

import { Delta, Spark } from "@/components/vl/primitives";

import { pointsAt, type PanelProps } from "../types";

const fmt = (n: number): string => n.toLocaleString("en-US");

/** Live counters from our own feeds (latest completed day against its recent normal) and the places the live memory flags as unusual. */
export default function LivePanel({ ctx }: PanelProps) {
  const live = ctx.data.live;
  if (!live) return <p className="hud-none">No live feed readings available.</p>;
  return (
    <>
      <ul className="hud-counters">
        {live.counters.map((c) => (
          <li key={c.key}>
            <Link href={c.href} className="hud-counter" title={`${c.label}: ${fmt(c.value)} ${c.unit}`}>
              <span className="hud-counter-label">{c.label}</span>
              <span className="hud-counter-n">{fmt(c.value)}</span>
              <span className="hud-counter-foot">
                <span className="hud-k">{c.unit}</span>
                {c.pct !== null && <Delta text={`${c.pct > 0 ? "+" : c.pct < 0 ? "−" : ""}${Math.abs(c.pct)}% vs usual`} sign={c.pct} />}
              </span>
              {c.spark.length > 1 && <Spark values={c.spark} label={`${c.label}, last ${c.spark.length} days`} />}
            </Link>
          </li>
        ))}
      </ul>
      {live.anomalies.length > 0 && (
        <>
          <p className="hud-cap">Unusual now</p>
          <ul className="hud-rows">
            {live.anomalies.map((a) => (
              <li key={a.id} {...pointsAt(ctx, a.iso)}>
                <Link href="/live" className="hud-row">
                  <span className={`hud-flag hud-flag-${a.direction}`}>{a.direction === "above" ? "▲ above" : "▼ below"}</span>
                  <span className="hud-row-text">{a.sentence}</span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
