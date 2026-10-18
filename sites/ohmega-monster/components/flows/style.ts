// One hue per ship class and per commodity, the same in the layer panel, the canvas and the HUD panel (maximum delineation: nine
// hues spread around the wheel, none of them a theme colour). Ships are observed AIS and drawn as moving dots on thin lanes; grain and
// money are annual statistics and drawn as slow, wide, translucent arcs, so a hue is never the only thing telling the two apart.

import type { CommodityId, LayerId, ShipId } from "./types";

export const SHIP_IDS: readonly ShipId[] = ["tanker", "lng", "bulk", "container", "cargo"];
export const COMMODITY_IDS: readonly CommodityId[] = ["wheat", "maize", "soy"];

export const LAYER_LABEL: Record<LayerId, string> = {
  tanker: "Tankers",
  lng: "Gas carriers",
  bulk: "Bulk carriers",
  container: "Container ships",
  cargo: "Other cargo ships",
  wheat: "Wheat",
  maize: "Corn",
  soy: "Soy",
  money: "Money (goods exports)",
};

// The coast is the site's amber and the anomaly rings are rose and blue, so no ship class sits near those three.
const DARK: Record<LayerId, string> = {
  tanker: "#ff5d4a",
  lng: "#36d6e7",
  bulk: "#a78bfa",
  container: "#b5e853",
  cargo: "#8fa3b8",
  wheat: "#ffd34d",
  maize: "#f28c28",
  soy: "#2fb36e",
  money: "#f2f2f2",
};

const PAPER: Record<LayerId, string> = {
  tanker: "#c4301c",
  lng: "#0a8fa3",
  bulk: "#5b49d6",
  container: "#5e8f1f",
  cargo: "#5f7388",
  wheat: "#9c8300",
  maize: "#b5651d",
  soy: "#12804a",
  money: "#2b2b2b",
};

export const colorOf = (id: LayerId, light: boolean): string => (light ? PAPER : DARK)[id];

/** Typical speed over the ground by class, kilometres a day (12 to 18 knots). With the lane's observed rate it gives how many ships
 *  are on the lane at once (rate x length / speed), which is the number of dots drawn, before the global thinning. */
export const SHIP_KM_PER_DAY: Record<ShipId, number> = { tanker: 530, lng: 750, bulk: 540, container: 800, cargo: 600 };

export const ANOMALY: Record<"above" | "below", string> = { above: "#d4568a", below: "#4a7fd0" }; // the same pair /live uses (lib/live-shared ANOMALY_COLOR)

export const isShip = (id: LayerId): id is ShipId => (SHIP_IDS as readonly string[]).includes(id);
