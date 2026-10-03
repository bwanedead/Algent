"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

// Keyboard half of the day navigator: ← goes to the previous (older) report, → to the next (newer).
// Stands down while typing, with a modifier held, or while any dialog (a popover) is open.
export default function DayKeys({ prev, next }: { prev: string | null; next: string | null }) {
  const router = useRouter();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      const href = e.key === "ArrowLeft" ? prev : e.key === "ArrowRight" ? next : null;
      if (!href) return;
      const t = e.target;
      if (t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      if (document.querySelector('[role="dialog"]')) return;
      e.preventDefault();
      router.push(href);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [prev, next, router]);
  return null;
}
