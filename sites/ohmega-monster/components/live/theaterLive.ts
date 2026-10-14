// The hand-off between a theater's "Live now" strip and that theater's map. The two sit in different places of a (server-rendered)
// page, so they meet in a small external store keyed by a scope id (the theater section's anchor / the dossier's theater id):
//   - the strip loads the theater's live objects (useTheaterObjects.ts) and publishes them,
//   - the map announces that it is up; it draws NO live objects by default,
//   - a "Show me" press on the strip files a request (a group) the map answers by drawing only that group (objectLayers.ts, subtly) and
//     fitting the view to it; a second press (the button then reads "Hide") clears it, and the map reports which group it shows (`shown`).
// Client-only; no lib/store.

import { useSyncExternalStore } from "react";

import { NO_OBJECTS, type Group, type Shaped } from "./theaterObjects";

export type ShowRequest = { nonce: number; group: Group };
/** `shown`: the one group the map draws because of a "Show me" press (null: none; the map draws no live objects by default). */
export type ScopeState = { live: Shaped; map: boolean; request: ShowRequest | null; shown: Group | null };

const EMPTY: ScopeState = { live: NO_OBJECTS, map: false, request: null, shown: null };
const scopes = new Map<string, ScopeState>();
const listeners = new Set<() => void>();
let nonce = 0;

function patch(scope: string, next: Partial<ScopeState>) {
  scopes.set(scope, { ...(scopes.get(scope) ?? EMPTY), ...next });
  listeners.forEach((l) => l());
}

export const publishLive = (scope: string, live: Shaped) => patch(scope, { live });
export const setMapUp = (scope: string, map: boolean) => patch(scope, { map });
export const setShown = (scope: string, shown: Group | null) => patch(scope, { shown });
export const requestShow = (scope: string, group: Group) => patch(scope, { request: { nonce: ++nonce, group } });

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => void listeners.delete(l);
};

/** The scope's current state (a stable object until something changes); the empty state when no scope id is given. */
export function useScope(scope: string | undefined): ScopeState {
  return useSyncExternalStore(
    subscribe,
    () => (scope ? scopes.get(scope) ?? EMPTY : EMPTY),
    () => EMPTY,
  );
}
