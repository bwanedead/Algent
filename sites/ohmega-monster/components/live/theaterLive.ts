// The hand-off between a theater's "Live now" strip and that theater's map. The two sit in different places of a (server-rendered)
// page, so they meet in a small external store keyed by a scope id (the theater section's anchor / the dossier's theater id):
//   - the strip publishes the live events it lists (the relevance logic is lib/live-shared `liveTouching`, run on the server),
//   - the map announces that it is up and draws those events, and
//   - a "Show me" press on the strip files a request the map answers by flying to the object and opening its popup.
// Client-only; no lib/store.

import { useSyncExternalStore } from "react";

import type { Item } from "./liveItems";

export type ShowRequest = { nonce: number; id: string };
export type ScopeState = { events: Item[]; map: boolean; request: ShowRequest | null };

const EMPTY: ScopeState = { events: [], map: false, request: null };
const scopes = new Map<string, ScopeState>();
const listeners = new Set<() => void>();
let nonce = 0;

function patch(scope: string, next: Partial<ScopeState>) {
  scopes.set(scope, { ...(scopes.get(scope) ?? EMPTY), ...next });
  listeners.forEach((l) => l());
}

export const publishEvents = (scope: string, events: Item[]) => patch(scope, { events });
export const setMapUp = (scope: string, map: boolean) => patch(scope, { map });
export const requestShow = (scope: string, id: string) => patch(scope, { request: { nonce: ++nonce, id } });

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
