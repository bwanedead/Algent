// The HUD board as pure data: which panels sit in which slot around the globe, and the operations on that layout. No React, no I/O, so it
// is easy to reason about (and to test): every function takes a board and returns a new one. The hook that persists it is useBoard.ts;
// the panel types themselves are registered in registry.tsx.

export type SlotId = "top" | "left" | "right" | "bottom";
export const SLOTS: SlotId[] = ["top", "left", "right", "bottom"];
export const SLOT_LABEL: Record<SlotId, string> = { top: "Top", left: "Left", right: "Right", bottom: "Bottom" };

/** Board panels exist once each ("singleton"); context panels belong to one place picked on the globe (`ref` = ISO code or theater id). */
export type SingletonKind = "daily" | "theaters" | "pulses" | "live" | "coming" | "sanctions" | "trader" | "tweets" | "flows" | "attacks" | "gnss";
export type ContextKind = "country" | "theater";
export type PanelKind = SingletonKind | ContextKind;

export const CONTEXT_KINDS: readonly ContextKind[] = ["country", "theater"];
export const isContext = (k: PanelKind): k is ContextKind => (CONTEXT_KINDS as readonly string[]).includes(k);

export type PanelState = {
  /** `kind` for a singleton, `kind:ref` for a context panel. */
  id: string;
  kind: PanelKind;
  ref: string;
  /** A pinned context panel stays when the next place is picked; an unpinned one is replaced by it and is not remembered. */
  pinned: boolean;
  collapsed: boolean;
};

export type Board = Record<SlotId, PanelState[]>;

/** The element id of a panel's frame (the colon in a context panel's id is not safe in selectors). */
export const domId = (id: string): string => `hud-panel-${id.replace(/[^\w-]/g, "_")}`;

export const panelId = (kind: PanelKind, ref: string): string => (isContext(kind) ? `${kind}:${ref}` : kind);

const make = (kind: PanelKind, ref = "", pinned = false): PanelState => ({ id: panelId(kind, ref), kind, ref, pinned, collapsed: false });

/** Where a panel type goes when it is added. */
export const HOME_SLOT: Record<PanelKind, SlotId> = {
  daily: "left", theaters: "left", pulses: "right", trader: "right", live: "top", coming: "bottom", sanctions: "bottom", tweets: "right", flows: "right", attacks: "bottom", gnss: "bottom", country: "right", theater: "right",
};

/** The board a first-time visitor sees. Tweets stay off it until there is a feed (see HudTweet in lib/globe/hud-data.ts). */
export function defaultBoard(): Board {
  return {
    top: [make("live")],
    left: [make("daily"), make("theaters")],
    right: [make("pulses"), make("trader")],
    bottom: [make("coming"), make("sanctions")],
  };
}

export const allPanels = (b: Board): PanelState[] => SLOTS.flatMap((s) => b[s]);
export const hasPanel = (b: Board, id: string): boolean => allPanels(b).some((p) => p.id === id);
const map = (b: Board, f: (list: PanelState[], slot: SlotId) => PanelState[]): Board => ({ top: f(b.top, "top"), left: f(b.left, "left"), right: f(b.right, "right"), bottom: f(b.bottom, "bottom") });

/** Add a panel to its home slot (no-op when it is already on the board). Context panels go first so they are the first thing seen. */
export function addPanel(b: Board, kind: PanelKind, ref = "", pinned = false): Board {
  const p = make(kind, ref, pinned);
  if (hasPanel(b, p.id)) return b;
  const slot = HOME_SLOT[kind];
  return { ...b, [slot]: isContext(kind) ? [p, ...b[slot]] : [...b[slot], p] };
}

/** A place was picked on the globe: show its panel. A pinned panel for it is left where it is (the caller focuses it); otherwise it
 *  replaces any unpinned panel of the same kind. */
export function openContext(b: Board, kind: ContextKind, ref: string): Board {
  const id = panelId(kind, ref);
  if (hasPanel(b, id)) return b;
  return addPanel(map(b, (l) => l.filter((p) => !(p.kind === kind && !p.pinned))), kind, ref);
}

export const removePanel = (b: Board, id: string): Board => map(b, (l) => l.filter((p) => p.id !== id));
const patch = (b: Board, id: string, f: (p: PanelState) => PanelState): Board => map(b, (l) => l.map((p) => (p.id === id ? f(p) : p)));
export const togglePin = (b: Board, id: string): Board => patch(b, id, (p) => ({ ...p, pinned: !p.pinned }));
export const setPinned = (b: Board, id: string, pinned: boolean): Board => patch(b, id, (p) => ({ ...p, pinned }));
export const toggleCollapse = (b: Board, id: string): Board => patch(b, id, (p) => ({ ...p, collapsed: !p.collapsed }));

/** Move a panel one place up or down inside its slot, or to the end of another slot. */
export function movePanel(b: Board, id: string, to: "up" | "down" | SlotId): Board {
  const from = SLOTS.find((s) => b[s].some((p) => p.id === id));
  if (!from) return b;
  const panel = b[from].find((p) => p.id === id) as PanelState;
  if (to === "up" || to === "down") {
    const list = [...b[from]];
    const i = list.findIndex((p) => p.id === id);
    const j = to === "up" ? i - 1 : i + 1;
    if (j < 0 || j >= list.length) return b;
    [list[i], list[j]] = [list[j], list[i]];
    return { ...b, [from]: list };
  }
  if (to === from) return b;
  const without = removePanel(b, id);
  return { ...without, [to]: [...without[to], panel] };
}

// ---- persistence (the hook owns the storage; these two are pure) ----------------------------------------------------------------

const KINDS: readonly PanelKind[] = ["daily", "theaters", "pulses", "live", "coming", "sanctions", "trader", "tweets", "flows", "attacks", "gnss", "country", "theater"];

/** The board as it is remembered: every panel but the unpinned context ones (those are only a look at a place). */
export function toSaved(b: Board): Board {
  return map(b, (l) => l.filter((p) => !isContext(p.kind) || p.pinned));
}

/** A board read back from storage, or null when it is not a usable board (the default is then shown). Unknown kinds and repeats are dropped. */
export function fromSaved(raw: unknown): Board | null {
  if (typeof raw !== "object" || raw === null) return null;
  const r = raw as Record<string, unknown>;
  const seen = new Set<string>();
  const out: Board = { top: [], left: [], right: [], bottom: [] };
  for (const slot of SLOTS) {
    const list = r[slot];
    if (!Array.isArray(list)) return null;
    for (const item of list) {
      if (typeof item !== "object" || item === null) continue;
      const p = item as Record<string, unknown>;
      const kind = p.kind as PanelKind;
      const ref = typeof p.ref === "string" ? p.ref.slice(0, 40) : "";
      if (!KINDS.includes(kind) || (isContext(kind) && !ref)) continue;
      const id = panelId(kind, ref);
      if (seen.has(id)) continue;
      seen.add(id);
      out[slot].push({ id, kind, ref: isContext(kind) ? ref : "", pinned: isContext(kind) ? p.pinned === true : false, collapsed: p.collapsed === true });
    }
  }
  return out;
}
