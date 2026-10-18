"use client";

import { useMemo } from "react";

import { fmtRate, fmtTonnes, fmtUsd } from "@/components/flows/scene";
import { colorOf, LAYER_LABEL, SHIP_IDS } from "@/components/flows/style";
import type { FlowLane, FlowsDoc, TradeFlow } from "@/components/flows/types";
import { useFlows } from "@/components/flows/useFlows";

import type { PanelProps } from "../types";

const placeName = (doc: FlowsDoc, id: string): string => doc.ais.places.find((p) => p.id === id)?.label ?? id.replace(/_/g, " ");

function Swatches({ lane }: { lane: FlowLane }) {
  return (
    <span aria-hidden="true">
      {SHIP_IDS.filter((c) => (lane.by[c] ?? 0) > 0).map((c) => <span key={c} className="fl-sw" style={{ display: "inline-block", width: 8, height: 8, marginRight: 3, background: colorOf(c, false) }} title={LAYER_LABEL[c]} />)}
    </span>
  );
}

function TradeRows({ doc, flows }: { doc: FlowsDoc; flows: TradeFlow[] }) {
  return (
    <ul className="hud-rows hud-table">
      {[...flows].sort((a, b) => b.usd - a.usd).slice(0, 4).map((f) => (
        <li key={`${f.from}>${f.to}`}>
          <span className="hud-row">
            <span className="hud-row-text">{doc.places[f.from]?.name ?? f.from} to {doc.places[f.to]?.name ?? f.to}</span>
            <span className="hud-k">{f.t > 0 ? `${fmtTonnes(f.t)}, ` : ""}{fmtUsd(f.usd)}, {f.period}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** The circulation in numbers: chokepoint traffic from our own AIS (with places outside their own normal flagged), the busiest lanes,
 *  and the largest grain and money flows from public trade statistics. The same document the globe's "Flows" layer draws. */
export default function FlowsPanel(_props: PanelProps) {
  const { doc, status } = useFlows(true);
  const chokepoints = useMemo(() => (doc ? doc.ais.places.filter((p) => p.kind === "chokepoint").sort((a, b) => b.r7 - a.r7) : []), [doc]);
  const lanes = useMemo(() => (doc ? [...doc.ais.lanes].sort((a, b) => (b.r7 || b.r30) - (a.r7 || a.r30)).slice(0, 6) : []), [doc]);
  if (!doc) return <p className="hud-none">{status === "none" ? "No flow data has been published yet." : "Loading flows..."}</p>;
  const grain = Object.entries(doc.grain?.commodities ?? {});
  return (
    <>
      <p className="hud-cap">Chokepoints · ships a day, our AIS</p>
      {chokepoints.length > 0 ? (
        <ul className="hud-rows hud-table">
          {chokepoints.map((p) => (
            <li key={p.id}>
              <span className="hud-row">
                {p.dir ? <span className={`hud-flag hud-flag-${p.dir}`}>{p.dir === "above" ? "▲ above" : "▼ below"}</span> : null}
                <span className="hud-row-text">{p.label}</span>
                <span className="hud-k" title={p.usual !== undefined ? `Usually ${fmtRate(p.usual)} a day; ${fmtRate(p.last ?? 0)} on ${p.day}` : "No normal learned yet"}>{fmtRate(p.r7)}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : <p className="hud-none">Nothing counted yet.</p>}
      {lanes.length > 0 && (
        <>
          <p className="hud-cap">Busiest lanes</p>
          <ul className="hud-rows hud-table">
            {lanes.map((l) => (
              <li key={`${l.a}>${l.b}`}>
                <span className="hud-row">
                  <Swatches lane={l} />
                  <span className="hud-row-text">{placeName(doc, l.a)} to {placeName(doc, l.b)}</span>
                  <span className="hud-k">{fmtRate(l.r7 || l.r30)}</span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {grain.map(([id, block]) => block && (
        <div key={id}>
          <p className="hud-cap">{block.label} · UN trade statistics</p>
          <TradeRows doc={doc} flows={block.flows} />
        </div>
      ))}
      {doc.money && (
        <>
          <p className="hud-cap">Goods exports · UN trade statistics</p>
          <TradeRows doc={doc} flows={doc.money.flows} />
        </>
      )}
      <p className="hud-foot">
        Ships as of {doc.as_of.slice(0, 16).replace("T", " ")} UTC, watched {doc.ais.days} {doc.ais.days === 1 ? "day" : "days"}; only what coastal receivers hear.
        Grain and money are a year of reported trade, not live. Turn on Flows in the globe&apos;s controls to see them move.
      </p>
    </>
  );
}
