"use client";

import { useEffect, useRef, useState } from "react";

import "./fresh.css";

// "New since your last visit": a small dot on a hub row or card. The reader's last-seen stamp for each item lives in localStorage
// (`ohm:seen:<id>`), written when they follow the link the dot sits in. With no stored stamp (a first visit, or storage blocked) an
// item shows the dot only if it is not stale, so a stranger is not met by a dot on everything. Every storage access is guarded:
// without storage the page is simply dot-free.
const KEY = "ohm:seen:";

export default function NewDot({ id, stamp, stale = false }: { id: string; stamp: string; stale?: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [on, setOn] = useState(false);
  useEffect(() => {
    let seen: string | null = null;
    try {
      seen = window.localStorage.getItem(KEY + id);
    } catch {
      seen = null;
    }
    setOn(seen === null ? !stale : stamp > seen);
    const link = ref.current?.closest("a");
    if (!link) return;
    const mark = () => {
      try {
        window.localStorage.setItem(KEY + id, stamp);
      } catch {
        /* storage unavailable: nothing to remember */
      }
    };
    link.addEventListener("click", mark);
    return () => link.removeEventListener("click", mark);
  }, [id, stamp, stale]);
  return on ? <span ref={ref} className="fresh-dot" role="img" aria-label="New since your last visit" title="New since your last visit" /> : <span ref={ref} hidden />;
}
