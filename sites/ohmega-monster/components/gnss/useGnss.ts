"use client";

// Loads the published `gnss` document (a small JSON object in the public live bucket, rebuilt hourly) while the layer is wanted and the tab is
// visible. "none" means nothing is published yet (or the fetch failed): the layer says so rather than drawing an empty globe.

import { useEffect, useState } from "react";

import { fetchSnapshot } from "@/lib/live-shared";

import type { GnssDoc } from "./types";

const REFRESH_MS = 10 * 60 * 1000;

export type GnssState = { doc: GnssDoc | null; status: "idle" | "loading" | "ok" | "none" };

export function useGnss(wanted: boolean): GnssState {
  const [state, setState] = useState<GnssState>({ doc: null, status: "idle" });
  useEffect(() => {
    if (!wanted) return;
    let dead = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const load = async () => {
      if (document.hidden) { timer = setTimeout(() => { void load(); }, REFRESH_MS); return; }
      const doc = await fetchSnapshot<GnssDoc>("gnss");
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
