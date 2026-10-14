"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { groupBounds, objectLayers } from "@/components/live/objectLayers";
import { setMapUp, setShown, useScope } from "@/components/live/theaterLive";
import type { Bounds } from "./geo";
import type { DailyDevelopment, TheaterMap } from "@/lib/daily";

import GeoMapStatic from "./GeoMapStatic";
import LiveMap, { type MapStatus } from "./LiveMap";
import { theaterLayers } from "./theaterLayers";

// THE map of the site: daily-report theaters and dossier maps both draw through this. It is the interactive map
// (MapLibre over OpenFreeMap tiles, see LiveMap.tsx) showing the backend's data: numbered marks that match the
// development list, disputed/occupied areas, chokepoint readings. While it loads a neutral skeleton holds the place (no static map to flash
// before the real one); the home-drawn SVG (GeoMapStatic) shows only without JS (<noscript>) or WebGL, and in full
// (with its own legend and credit) if the interactive map cannot start. The SVG also stays the source for social stills.
// The theater's live objects (military aircraft, tankers, military vessels in the theater's box: its "Live now" strip, see
// components/live/theaterLive.ts) are NOT drawn by default: this map is about where the theater's events happened. The strip's "Show me"
// draws only that one group, small and muted (a second press, "Hide", clears it) and fits the map to it (LiveMap `focus`); an optional
// "Show nearby traffic" tool draws all three groups the same quiet way. The strip owns the loading, so the map makes no request of its own.
// The purple disputed/occupied areas have a key chip that is also their on/off switch. Both switches are remembered per browser.
// Doctrine: docs/ethos/information-ergonomics-ethos.md. Spec: docs/architecture/intel-desk.md "Maps".

const SHOW_ALL: string[] = [];
const HIDE_AREAS = ["disputed"];
const NEARBY_KEY = "ohmega-theater-nearby";
const AREAS_KEY = "ohmega-theater-areas";

/** A per-browser on/off preference; storage may be blocked (private window), then it simply applies to this visit. */
function usePref(key: string, initial: boolean): [boolean, (v: boolean) => void] {
  const [on, setOn] = useState(initial);
  useEffect(() => {
    try {
      const v = localStorage.getItem(key);
      if (v === "1" || v === "0") setOn(v === "1");
    } catch { /* storage blocked: keep the default */ }
  }, [key]);
  return [on, (v) => {
    setOn(v);
    try { localStorage.setItem(key, v ? "1" : "0"); } catch { /* storage blocked */ }
  }];
}

const AREAS_TIP = "Areas whose control is contested or occupied, e.g. Russian-held parts of Ukraine; tap an area for details. Click to hide or show them.";
const NEARBY_TIP = "Draw all the military aircraft, tankers and military vessels counted in the strip above, small and muted. Off by default; the strip's Show me draws one group.";

const BASEMAP_CREDIT = "Interactive basemap: OpenFreeMap, © OpenMapTiles, data © OpenStreetMap contributors.";

export default function GeoMap({ map, developments, label, initialK, liveScope }: { map: TheaterMap | null; developments: DailyDevelopment[]; label?: string; initialK?: number; liveScope?: string }) {
  const [status, setStatus] = useState<MapStatus>("loading");
  const spec = useMemo(() => (map ? theaterLayers(map, developments) : null), [map, developments]);
  const { live, request, shown } = useScope(liveScope);
  const [nearby, setNearby] = usePref(NEARBY_KEY, false);
  const [areasOn, setAreasOn] = usePref(AREAS_KEY, true);
  const [focus, setFocus] = useState<{ nonce: number; bounds: Bounds } | null>(null);
  // Nothing by default; a "Show me" group alone; or everything counted when the nearby-traffic tool is on.
  const drawn = useMemo(() => (nearby ? live.objs : shown ? live.objs.filter((o) => o.group === shown) : []), [nearby, shown, live.objs]);
  const liveSpecs = useMemo(() => objectLayers(drawn), [drawn]);
  const layers = useMemo(() => (spec ? [...spec.layers, ...liveSpecs] : []), [spec, liveSpecs]);
  const fig = useRef<HTMLElement>(null);
  const seen = useRef(request?.nonce ?? 0); // a request filed before this map existed is not replayed
  const ready = status === "ready";

  useEffect(() => {
    if (!liveScope || !ready) return;
    setMapUp(liveScope, true);
    return () => {
      setMapUp(liveScope, false);
      setShown(liveScope, null);
    };
  }, [liveScope, ready]);

  // A "Show me" press: a first press draws that group and fits the map to it (bringing the map into view first: the strip sits above
  // it); a second press on the same group clears it.
  useEffect(() => {
    if (!liveScope || !request || request.nonce <= seen.current) return;
    seen.current = request.nonce;
    if (shown === request.group) {
      setShown(liveScope, null);
      return;
    }
    setShown(liveScope, request.group);
    const frame = groupBounds(live.objs, request.group);
    if (!frame) return;
    setFocus({ nonce: request.nonce, bounds: frame });
    const calm = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    fig.current?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "nearest" });
  }, [request?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!map || !spec) return null;
  if (status === "failed") return <GeoMapStatic map={map} developments={developments} label={label} initialK={initialK} />;

  const name = label ?? `Map: ${map.points.length} marked place${map.points.length === 1 ? "" : "s"}, numbered as in the timeline.`;
  const hasAreas = map.disputed.length > 0;
  const aspect = Math.min(1.9, Math.max(1.1, map.width / map.height));
  return (
    <figure className="geo-map geo-map-int" ref={fig}>
      <LiveMap
        layers={layers}
        bounds={spec.bounds}
        label={name}
        aspect={aspect}
        tilt
        maxZoom={8}
        items={spec.items}
        itemsLabel="Marked places"
        focus={focus}
        hidden={areasOn ? SHOW_ALL : HIDE_AREAS}
        theaterStyle
        tools={
          <>
            {hasAreas && (
              <button type="button" className="lm-btn" aria-pressed={areasOn} title={AREAS_TIP} onClick={() => setAreasOn(!areasOn)}>
                <span aria-hidden="true" style={{ display: "inline-block", width: 12, height: 12, marginRight: 6, verticalAlign: "-1px", border: "1.5px dashed #7a4fa3", background: "rgba(122,79,163,0.3)", opacity: areasOn ? 1 : 0.4 }} />
                Disputed / occupied
              </button>
            )}
            {liveScope && live.objs.length > 0 && (
              <button type="button" className="lm-btn" aria-pressed={nearby} title={NEARBY_TIP} onClick={() => setNearby(!nearby)}>
                Show nearby traffic
              </button>
            )}
          </>
        }
        onStatus={setStatus}
        fallback={<GeoMapStatic map={map} developments={developments} label={name} initialK={initialK} bare />}
        credit={
          <>
            <span className="geo-micro">Numbers match the timeline. Solid mark: researched; hollow: reported.{hasAreas ? " Dashed purple areas: disputed or occupied territory; select one for its status and source." : ""}</span>
            {drawn.length > 0 && <span className="geo-micro"> Small arrows: live military aircraft (purple), tankers (amber) and military or law-enforcement vessels (red) in the theater, from the strip above; a faint numbered circle is several close together.</span>}
            <br />
            {map.credit} {BASEMAP_CREDIT}
          </>
        }
      />
    </figure>
  );
}
