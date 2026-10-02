"use client";

// "Since your last visit": the one thing the accent colour means on the Situation Room. The last
// visit lives in localStorage (guarded: storage can be blocked or throw), and anything newer than it
// wears the accent dot. First visit = the last 7 days. A "visit" is a session: a reload within 30
// minutes keeps the same marker, so the dots do not vanish on refresh.

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

const KEY = "ohmega.intel.visit";
const SESSION_MS = 30 * 60_000;
const FIRST_VISIT_MS = 7 * 86_400_000;

export type Since = { at: number; first: boolean };
const SinceContext = createContext<Since | null>(null);

function readSince(now: number, touch: boolean): Since {
  let prev: number | null = null;
  let cur: number | null = null;
  try {
    const o: unknown = JSON.parse(window.localStorage.getItem(KEY) ?? "null");
    if (typeof o === "object" && o !== null) {
      const r = o as { prev?: unknown; cur?: unknown };
      if (typeof r.prev === "number" && Number.isFinite(r.prev)) prev = r.prev;
      if (typeof r.cur === "number" && Number.isFinite(r.cur)) cur = r.cur;
    }
  } catch {
    /* storage blocked or corrupt: behave as a first visit */
  }
  if (cur !== null && now - cur > SESSION_MS) prev = cur; // a new session: the last one becomes "your last visit"
  if (touch) {
    try {
      window.localStorage.setItem(KEY, JSON.stringify({ prev, cur: now }));
    } catch {
      /* ignore */
    }
  }
  return prev === null ? { at: now - FIRST_VISIT_MS, first: true } : { at: prev, first: false };
}

/** Provides the last-visit time to markers below it. `touch={false}` reads without recording a visit (home teaser). */
export function SituationVisitProvider({ children, touch = true }: { children: ReactNode; touch?: boolean }) {
  const [since, setSince] = useState<Since | null>(null); // null until mounted: server and first client render agree
  useEffect(() => {
    setSince(readSince(Date.now(), touch));
  }, [touch]);
  return <SinceContext.Provider value={since}>{children}</SinceContext.Provider>;
}

export const useSince = (): Since | null => useContext(SinceContext);

export function isNewSince(at: string, since: Since | null): boolean {
  if (!since) return false;
  const t = Date.parse(at);
  return Number.isFinite(t) && t > since.at;
}

/** The accent "new" dot; renders only when `at` is after the reader's last visit. */
export function NewDot({ at }: { at: string }) {
  const since = useSince();
  if (!isNewSince(at, since)) return null;
  return <span className="sit-new" role="img" aria-label="New since your last visit" title="New since your last visit" />;
}

const stamp = (t: number) => `${new Date(t).toISOString().slice(0, 16).replace("T", " ")} UTC`;

/** How many things changed since the last visit. `compact` (the home teaser) says nothing when nothing did. */
export function SituationSince({ times, compact = false }: { times: string[]; compact?: boolean }) {
  const since = useSince();
  if (!since) return null;
  const n = times.filter((t) => isNewSince(t, since)).length;
  if (compact) {
    if (n === 0) return null;
    return (
      <span className="sit-since sit-since-compact">
        <span className="sit-new" aria-hidden="true" /> {n} new {since.first ? "this week" : "since your last visit"}
      </span>
    );
  }
  return (
    <span className="sit-since">
      {n > 0 && <span className="sit-new" aria-hidden="true" />}
      <b className={n > 0 ? "sit-accent" : "intel-num-sm"}>{n}</b> {n === 1 ? "change" : "changes"}{" "}
      <span className="intel-micro">{since.first ? "in the last 7 days" : `since your last visit · ${stamp(since.at)}`}</span>
    </span>
  );
}
