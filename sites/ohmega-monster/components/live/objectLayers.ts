// A theater's live objects (theaterObjects.ts) as map layers: the same heading-rotated arrows /live draws (its icon images and
// colours, via TrackLayers.addTrackIcons and entities.iconOf/colorOf), one clustering layer per group so a crowd of tankers reads as a
// counted bubble until zoomed in. A click opens the same description /live gives the object (entities.describe). Client-safe.

import { collection, pointFeature, boundsOf, type Bounds, type LngLat } from "@/components/map/geo";
import type { LayerSpec } from "@/components/map/mapLayers";

import { colorOf, describe, iconOf, reckon } from "./entities";
import { GROUPS, type Group, type Obj } from "./theaterObjects";
import { addTrackIcons, SOURCE } from "./TrackLayers";

export const objectGroupId = (g: Group) => `obj-${g}`;

export function objectLayers(objs: Obj[]): LayerSpec[] {
  const now = Date.now() / 1000;
  return GROUPS.flatMap((g): LayerSpec[] => {
    const mine = objs.filter((o) => o.group === g.key);
    if (mine.length === 0) return [];
    const features = mine.map(({ e }) => {
      const d = describe(e, now);
      return pointFeature(reckon(e, now), { id: `obj:${e.kind}:${e.id}`, h: e.hdg, ic: iconOf(e), col: colorOf(e), kind: d.kind, title: d.title, lines: d.lines.join("\n"), src: e.kind });
    });
    return [{
      group: objectGroupId(g.key), kind: "icons", cluster: true, color: g.color, data: collection(features), images: addTrackIcons,
      popup: (p) => {
        const src = SOURCE[p.src === "ship" ? "ship" : "air"];
        return { kind: String(p.kind), title: String(p.title), lines: String(p.lines ?? "").split("\n").filter(Boolean), source: src.name, url: src.url };
      },
    }];
  });
}

/** The frame holding every drawn object of one group, or null when it has none. */
export function groupBounds(objs: Obj[], group: Group): Bounds | null {
  return boundsOf(objs.filter((o) => o.group === group).map((o): LngLat => [o.e.lon, o.e.lat]));
}
