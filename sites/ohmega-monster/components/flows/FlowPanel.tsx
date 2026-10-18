"use client";

// The flow layer's legend and switches, in the globe's corner: one line per layer (swatch, name, a number) that is also its on/off
// switch, grouped by where the data comes from (our own AIS for ships; public trade statistics for grain and money), with the
// coverage caveat and the "as of" in plain words. Nothing here draws; it only reports what the canvas is showing.

import { useState } from "react";

import { fmtRate, type Scene } from "./scene";
import { colorOf, COMMODITY_IDS, LAYER_LABEL, SHIP_IDS } from "./style";
import type { FlowsDoc, LayerId } from "./types";

function asOf(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().slice(0, 10)} ${d.toISOString().slice(11, 16)} UTC`;
}

function tradeYear(doc: FlowsDoc, layers: LayerId[]): string {
  const years = new Set<string>();
  for (const l of layers) {
    const flows = l === "money" ? doc.money?.flows : doc.grain?.commodities[l as "wheat" | "maize" | "soy"]?.flows;
    for (const f of flows ?? []) years.add(f.period);
  }
  const list = [...years].sort();
  return list.length === 0 ? "" : list.length === 1 ? list[0] : `${list[0]} to ${list[list.length - 1]}`;
}

export default function FlowPanel({ doc, scene, available, on, toggle, light }: {
  doc: FlowsDoc;
  scene: Scene;
  available: LayerId[];
  on: ReadonlySet<LayerId>;
  toggle: (id: LayerId) => void;
  light: boolean;
}) {
  const [open, setOpen] = useState(true);
  const has = (id: LayerId) => available.includes(id);
  const row = (id: LayerId, value: string) => (
    <li key={id}>
      <button type="button" className={on.has(id) ? "is-on" : ""} aria-pressed={on.has(id)} onClick={() => toggle(id)}>
        <span className="fl-sw" style={{ background: colorOf(id, light) }} aria-hidden="true" />
        <span className="fl-name">{LAYER_LABEL[id]}</span>
        <span className="fl-val">{value}</span>
      </button>
    </li>
  );
  const ships = SHIP_IDS.filter(has);
  const grains = COMMODITY_IDS.filter(has);
  const anomalies = scene.places.filter((p) => p.dir).length;
  const year = tradeYear(doc, [...grains, ...(has("money") ? (["money"] as LayerId[]) : [])]);
  return (
    <div className={open ? "fl-panel" : "fl-panel is-min"} role="group" aria-label="Flows">
      <div className="fl-bar">
        <span>Flows</span>
        <button type="button" className="fl-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>{open ? "Hide" : "Flows"}</button>
      </div>
      {open && (
        <>
          <p className="fl-head">Ships <i>our AIS, moving now</i></p>
          {ships.length > 0 ? (
            <ul>{ships.map((c) => row(c, `${fmtRate(scene.passages[c] ?? 0)}/day`))}</ul>
          ) : (
            <p className="fl-note">No lane traffic counted yet.</p>
          )}
          {ships.length > 0 && (
            <p className="fl-note">
              Dots are ships heard on the lanes between {"chokepoints and port regions"}; busier lanes carry more dots and breathe faster.
              {scene.thin > 1.05 ? ` 1 dot is about ${Math.round(scene.thin)} ships.` : " 1 dot is 1 ship."} The number is ships a day passing the
              watched chokepoints.
            </p>
          )}
          {anomalies > 0 && (
            <p className="fl-note fl-anom"><span className="fl-ring fl-ring-above" aria-hidden="true" /><span className="fl-ring fl-ring-below" aria-hidden="true" /> A ringed place is far above or below its own normal.</p>
          )}
          {(grains.length > 0 || has("money")) && (
            <>
              <p className="fl-head">Grain and money <i>UN trade statistics{year ? `, ${year}` : ""}, a year of trade</i></p>
              <ul>
                {grains.map((c) => row(c, `${doc.grain?.commodities[c]?.flows.length ?? 0} flows`))}
                {has("money") && row("money", `${doc.money?.flows.length ?? 0} flows`)}
              </ul>
              <p className="fl-note">Wide, slow arcs run exporter to buyer. They are not live shipments.</p>
            </>
          )}
          <p className="fl-foot">
            Ships as of {asOf(doc.as_of)}
            {doc.ais.days > 0 ? `, watched ${doc.ais.days} ${doc.ais.days === 1 ? "day" : "days"}` : ""}. Coverage is patchy: only what coastal AIS receivers hear.
            {doc.ais.learning && doc.ais.days > 0 ? " Still learning each place's normal." : ""}
          </p>
        </>
      )}
    </div>
  );
}
