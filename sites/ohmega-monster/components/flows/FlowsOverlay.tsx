"use client";

// Everything the globe needs for the "Flows" mode, in one element placed inside it: loads the document, builds the scene, owns which
// layers are switched on, and renders the canvas and the legend panel. It draws nothing when `active` is false and fetches nothing
// until it is first switched on. The globe hands in its camera refs (see FlowLayer).

import { useCallback, useEffect, useMemo, useState, type MutableRefObject } from "react";

import FlowLayer from "./FlowLayer";
import FlowPanel from "./FlowPanel";
import { availableLayers, buildScene } from "./scene";
import { SHIP_IDS } from "./style";
import type { LayerId } from "./types";
import { useFlows } from "./useFlows";

import "./flows.css";

export default function FlowsOverlay({ active, matrix, cam }: { active: boolean; matrix: MutableRefObject<number[]>; cam: MutableRefObject<{ zoom: number }> }) {
  const { doc, status } = useFlows(active);
  const scene = useMemo(() => (doc ? buildScene(doc) : null), [doc]);
  const available = useMemo(() => (doc ? availableLayers(doc) : []), [doc]);
  // The viewer's own switches; until they touch one, every ship class is on and grain and money are off (ships are our own observations).
  const [picked, setPicked] = useState<ReadonlySet<LayerId> | null>(null);
  const on = useMemo<ReadonlySet<LayerId>>(() => picked ?? new Set(available.filter((id) => (SHIP_IDS as readonly string[]).includes(id))), [picked, available]);
  const toggle = useCallback((id: LayerId) => {
    setPicked((prev) => {
      const next = new Set(prev ?? on);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, [on]);
  const [light, setLight] = useState(false);
  useEffect(() => {
    const read = () => setLight(document.documentElement.getAttribute("data-theme") === "paper");
    read();
    const mo = new MutationObserver(read);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);

  if (!active) return null;
  if (!doc || !scene) {
    return <p className="fl-status" role="status">{status === "none" ? "No flow data has been published yet." : "Loading flows..."}</p>;
  }
  return (
    <>
      <FlowLayer scene={scene} on={on} matrix={matrix} cam={cam} />
      <FlowPanel doc={doc} scene={scene} available={available} on={on} toggle={toggle} light={light} />
    </>
  );
}
