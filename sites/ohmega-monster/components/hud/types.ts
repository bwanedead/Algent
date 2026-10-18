// What a panel is handed: its place on the board and the shared context (the data, the globe's data, and the ways to talk back to the
// globe and the board). Panels depend on this file only, never on the board or the layout.

import type { GlobeData } from "@/lib/globe/data";
import type { HudData } from "@/lib/globe/hud-data";

import type { ContextKind, PanelState } from "./board";

export type HudCtx = {
  data: HudData;
  /** The globe's own per-country data (null when no daily is published). */
  globe: GlobeData | null;
  /** Outline these countries on the globe (a row is hovered or focused); [] clears. */
  hover: (isos: string[]) => void;
  /** Put this place on the board and keep it there (a pinned context panel). */
  track: (kind: ContextKind, ref: string) => void;
};

export type PanelProps = { panel: PanelState; ctx: HudCtx };

/** Props that make a row point at places on the globe while the pointer or focus is on it. */
export function pointsAt(ctx: HudCtx, isos: string[]) {
  return {
    onMouseEnter: () => ctx.hover(isos),
    onMouseLeave: () => ctx.hover([]),
    onFocus: () => ctx.hover(isos),
    onBlur: () => ctx.hover([]),
  };
}
