// The panel types: one entry each, a title and a self-contained body component that reads its data from the shared context. To add a
// panel type, write its component under panels/, add its kind to board.ts (+ its home slot) and register it here.

import type { ComponentType, ReactNode } from "react";

import IsoFlags from "@/components/IsoFlags";
import { countryTitle } from "@/components/globe/GlobePanel";

import type { PanelKind, PanelState, SingletonKind } from "./board";
import ComingPanel from "./panels/ComingPanel";
import DailyPanel from "./panels/DailyPanel";
import FlowsPanel from "./panels/FlowsPanel";
import LivePanel from "./panels/LivePanel";
import { CountryPanel, TheaterPanel } from "./panels/PlacePanels";
import PulsesPanel from "./panels/PulsesPanel";
import SanctionsPanel from "./panels/SanctionsPanel";
import TheatersPanel from "./panels/TheatersPanel";
import TraderPanel from "./panels/TraderPanel";
import TweetsPanel from "./panels/TweetsPanel";
import type { HudCtx, PanelProps } from "./types";

export type PanelDef = {
  /** Name in the "Panels" menu. */
  label: string;
  title: (p: PanelState, ctx: HudCtx) => ReactNode;
  Body: ComponentType<PanelProps>;
};

const fixed = (label: string, Body: ComponentType<PanelProps>): PanelDef => ({ label, title: () => label, Body });

export const REGISTRY: Record<PanelKind, PanelDef> = {
  daily: fixed("Today's report", DailyPanel),
  theaters: fixed("Theaters", TheatersPanel),
  pulses: fixed("Pulses", PulsesPanel),
  live: fixed("Live counters", LivePanel),
  coming: fixed("Coming up", ComingPanel),
  sanctions: fixed("Sanctions", SanctionsPanel),
  trader: fixed("Paper trader", TraderPanel),
  tweets: fixed("Tweets of the day", TweetsPanel),
  flows: fixed("Ships, grain and money", FlowsPanel),
  country: {
    label: "Country",
    title: (p, ctx) => <><IsoFlags codes={[p.ref]} /> {countryTitle(p.ref, ctx.globe)}</>,
    Body: CountryPanel,
  },
  theater: {
    label: "Theater",
    title: (p, ctx) => ctx.data.theaters.find((t) => t.id === p.ref)?.name ?? p.ref,
    Body: TheaterPanel,
  },
};

/** The kinds the "Panels" menu offers, in menu order (place panels are opened from the globe instead). */
export const MENU_KINDS: SingletonKind[] = ["daily", "theaters", "pulses", "live", "coming", "sanctions", "trader", "tweets", "flows"];
