"use client";

// Loads the published `satellite` document for the HUD panel (a small JSON object in the public live bucket, rebuilt by the server's daily pass).
// "none" means nothing is published yet (or the fetch failed): the panel says so.

import { useEffect, useState } from "react";

import { fetchSnapshot } from "@/lib/live-shared";
import type { SatelliteDoc } from "@/lib/satellite-shared";

const REFRESH_MS = 30 * 60 * 1000; // the document changes once a day

export type SatelliteState = { doc: SatelliteDoc | null; status: "idle" | "loading" | "ok" | "none" };

export function useSatellite(wanted: boolean): SatelliteState {
  const [state, setState] = useState<SatelliteState>({ doc: null, status: "idle" });
  useEffect(() => {
    if (!wanted) return;
    let dead = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const load = async () => {
      if (document.hidden) { timer = setTimeout(() => { void load(); }, REFRESH_MS); return; }
      const doc = await fetchSnapshot<SatelliteDoc>("satellite");
      if (dead) return;
      setState((prev) => (doc && doc.v === 1 ? { doc, status: "ok" } : { doc: prev.doc, status: prev.doc ? "ok" : "none" }));
      timer = setTimeout(() => { void load(); }, REFRESH_MS);
    };
    setState((prev) => (prev.status === "idle" ? { doc: null, status: "loading" } : prev));
    void load();
    return () => { dead = true; if (timer) clearTimeout(timer); };
  }, [wanted]);
  return state;
}
