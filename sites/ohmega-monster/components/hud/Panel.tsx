"use client";

// The frame every panel wears: a hairline box with a titled header and the controls (pin for a place, move, collapse, close).
// The body comes from the registry; nothing in here knows what a panel shows.

import { useState } from "react";

import { domId, isContext, SLOT_LABEL, SLOTS, type PanelState, type SlotId } from "./board";
import { REGISTRY } from "./registry";
import type { HudCtx } from "./types";

export type PanelActions = {
  pin: (id: string) => void;
  collapse: (id: string) => void;
  close: (id: string) => void;
  move: (id: string, to: "up" | "down" | SlotId) => void;
};

export default function Panel({ panel, slot, first, last, ctx, act, focused }: { panel: PanelState; slot: SlotId; first: boolean; last: boolean; ctx: HudCtx; act: PanelActions; focused: boolean }) {
  const [moving, setMoving] = useState(false);
  const def = REGISTRY[panel.kind];
  const place = isContext(panel.kind);
  const bodyId = `${domId(panel.id)}-body`;
  return (
    <section id={domId(panel.id)}className={`hud-panel${focused ? " is-focus" : ""}${place ? " is-place" : ""}${panel.pinned ? " is-pinned" : ""}`} aria-label={def.label}>
      <header className="hud-head">
        <h2 className="hud-title">{def.title(panel, ctx)}</h2>
        <div className="hud-ctl" role="group" aria-label="Panel controls">
          {place && (
            <button type="button" className={panel.pinned ? "is-on" : ""} aria-pressed={panel.pinned} onClick={() => act.pin(panel.id)} title={panel.pinned ? "Unpin: replace it when you pick another place" : "Pin: keep it on the board"}>
              {panel.pinned ? "Pinned" : "Pin"}
            </button>
          )}
          <button type="button" className={moving ? "is-on" : ""} aria-expanded={moving} onClick={() => setMoving((m) => !m)} title="Move this panel">Move</button>
          <button type="button" aria-expanded={!panel.collapsed} aria-controls={bodyId} onClick={() => act.collapse(panel.id)} title={panel.collapsed ? "Expand" : "Collapse"}>{panel.collapsed ? "+" : "−"}</button>
          <button type="button" onClick={() => act.close(panel.id)} aria-label={`Close ${def.label}`} title="Close">×</button>
        </div>
      </header>
      {moving && (
        <div className="hud-move" role="group" aria-label="Move panel">
          <button type="button" disabled={first} onClick={() => act.move(panel.id, "up")}>Up</button>
          <button type="button" disabled={last} onClick={() => act.move(panel.id, "down")}>Down</button>
          <span className="hud-move-sep" aria-hidden="true" />
          {SLOTS.filter((s) => s !== slot).map((s) => (
            <button key={s} type="button" onClick={() => { act.move(panel.id, s); setMoving(false); }}>To {SLOT_LABEL[s].toLowerCase()}</button>
          ))}
        </div>
      )}
      <div id={bodyId} className="hud-body" hidden={panel.collapsed}>
        <def.Body panel={panel} ctx={ctx} />
      </div>
    </section>
  );
}
