"use client";

// The /globe screen as a personal intelligence HUD: the globe in the middle and a board of panels docked around it (top and bottom
// strips, left and right columns; stacked under the globe on a phone). Picking a country or theater on the globe opens its panel;
// pinned panels stay, and the viewer's board is remembered in this browser (useBoard.ts). Layout operations are pure (board.ts), panel
// types are registered in registry.tsx, and the frame around each is Panel.tsx.

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import GlobeViewer from "@/components/globe/GlobeViewer";
import type { GlobeData, GlobePick } from "@/lib/globe/data";
import type { HudData } from "@/lib/globe/hud-data";

import { addPanel, allPanels, domId, hasPanel, movePanel, openContext, panelId, removePanel, setPinned, SLOTS, toggleCollapse, togglePin, type ContextKind, type SlotId } from "./board";
import Panel, { type PanelActions } from "./Panel";
import { MENU_KINDS, REGISTRY } from "./registry";
import type { HudCtx } from "./types";
import { useBoard } from "./useBoard";

import "./hud.css";

const FOCUS_MS = 1400;

export default function GlobeHud({ globe, hud }: { globe: GlobeData | null; hud: HudData }) {
  const { board, update, reset } = useBoard();
  const [pick, setPick] = useState<GlobePick | null>(null);
  const [hovered, setHovered] = useState<string[]>([]);
  const [focusId, setFocusId] = useState("");
  const [menu, setMenu] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const focus = useCallback((id: string) => {
    setFocusId(id);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setFocusId(""), FOCUS_MS);
  }, []);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  // Bring a newly shown or already pinned panel into view (only scrolls when it is off screen).
  useEffect(() => {
    if (!focusId) return;
    const calm = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById(domId(focusId))?.scrollIntoView({ block: "nearest", behavior: calm ? "auto" : "smooth" });
  }, [focusId]);

  const onPick = useCallback((p: GlobePick | null) => {
    setPick(p);
    if (!p) return;
    const kind: ContextKind = p.kind;
    const ref = p.kind === "country" ? p.iso : p.id;
    update((b) => openContext(b, kind, ref));
    focus(panelId(kind, ref));
  }, [update, focus]);

  const ctx = useMemo<HudCtx>(() => ({
    data: hud,
    globe,
    hover: setHovered,
    track: (kind, ref) => {
      update((b) => setPinned(addPanel(b, kind, ref, true), panelId(kind, ref), true));
      focus(panelId(kind, ref));
    },
  }), [hud, globe, update, focus]);

  const act = useMemo<PanelActions>(() => ({
    pin: (id) => update((b) => togglePin(b, id)),
    collapse: (id) => update((b) => toggleCollapse(b, id)),
    close: (id) => {
      setHovered([]);
      setPick((p) => (p && panelId(p.kind, p.kind === "country" ? p.iso : p.id) === id ? null : p));
      update((b) => removePanel(b, id));
    },
    move: (id, to) => { update((b) => movePanel(b, id, to)); focus(id); },
  }), [update, focus]);

  const count = (s: SlotId) => board[s].length;
  const placed = allPanels(board);

  return (
    <div className="hud">
      <div className="hud-bar" role="group" aria-label="Board">
        <span className="hud-bar-title">Board</span>
        <span className="hud-k">{placed.length} {placed.length === 1 ? "panel" : "panels"} · pinned places stay · saved in this browser</span>
        <div className="hud-bar-ctl">
          <button type="button" className={menu ? "is-on" : ""} aria-expanded={menu} aria-controls="hud-menu" onClick={() => setMenu((m) => !m)}>Panels</button>
          <button type="button" onClick={reset} title="Back to the default board">Reset</button>
        </div>
      </div>
      {menu && (
        <ul id="hud-menu" className="hud-menu" aria-label="Panels on the board">
          {MENU_KINDS.map((k) => {
            const on = hasPanel(board, k);
            return (
              <li key={k}>
                <button type="button" className={on ? "is-on" : ""} aria-pressed={on} onClick={() => update((b) => (on ? removePanel(b, k) : addPanel(b, k)))}>
                  <span className="hud-check" aria-hidden="true">{on ? "■" : "□"}</span> {REGISTRY[k].label}{k === "tweets" && !hud.tweets ? <span className="hud-k"> · no feed yet</span> : null}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <div className="hud-canvas" style={{ "--hud-l": count("left") > 0 ? "clamp(240px, 22vw, 320px)" : "0px", "--hud-r": count("right") > 0 ? "clamp(240px, 22vw, 320px)" : "0px" } as CSSProperties}>
        {SLOTS.map((slot) => (
          <div key={slot} className={`hud-slot hud-slot-${slot}`} data-empty={count(slot) === 0} aria-label={`${slot} panels`}>
            {board[slot].map((p, i) => (
              <Panel key={p.id} panel={p} slot={slot} first={i === 0} last={i === board[slot].length - 1} ctx={ctx} act={act} focused={focusId === p.id} />
            ))}
          </div>
        ))}
        <div className="hud-globe">
          <GlobeViewer data={globe} pick={pick} onPick={onPick} highlight={hovered} />
        </div>
      </div>
    </div>
  );
}
