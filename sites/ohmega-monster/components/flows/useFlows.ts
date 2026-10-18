"use client";

// Loads the published `flows` document (a small JSON object in the public live bucket, rebuilt by the server every 15 minutes) and
// refreshes it while it is wanted and the tab is visible. "none" means nothing is published yet (or the fetch failed): the layer says
// so rather than drawing an empty globe.

import { useEffect, useState } from "react";

import { fetchSnapshot } from "@/lib/live-shared";

import type { FlowsDoc } from "./types";

const REFRESH_MS = 5 * 60 * 1000;

export type FlowsState = { doc: FlowsDoc | null; status: "idle" | "loading" | "ok" | "none" };

export function useFlows(wanted: boolean): FlowsState {
  const [state, setState] = useState<FlowsState>({ doc: null, status: "idle" });
  useEffect(() => {
    if (!wanted) return;
    let dead = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const load = async () => {
      if (document.hidden) { timer = setTimeout(() => { void load(); }, REFRESH_MS); return; }
      const doc = await fetchSnapshot<FlowsDoc>("flows");
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
