"use client";

// THE plain-English hint. Two shapes, one behaviour:
//   <Tip text label>children</Tip>        the words get a dotted underline and open the hint (jargon in a line)
//   <Tip text label corner />             a small "i" for the corner of a tile (the tile itself is a button, so the
//                                         "i" sits beside it in a `.tip-host`, never inside it)
// Hover shows it on a mouse, a tap or Enter/Space toggles it on touch and keyboard; Esc, a tap elsewhere, scroll
// and resize close it. The bubble is portalled to <body> and positioned in the viewport, so a tile's overflow
// can never clip it. Explanations come from lib/glossary.ts or the backend (`plain` fields); see components/Term.tsx.

import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent as ReactKeyEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import "./tip.css";

const WIDTH = 260;
const EDGE = 8;
const GAP = 6;

type Spot = { x: number; y: number; above: boolean; w: number };

export default function Tip({ text, label, children, corner = false }: { text: string; label: string; children?: ReactNode; corner?: boolean }) {
  const [open, setOpen] = useState(false);
  const [spot, setSpot] = useState<Spot | null>(null);
  const ref = useRef<HTMLSpanElement>(null);
  const pointer = useRef("mouse");
  const id = useId();

  const place = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const w = Math.min(WIDTH, window.innerWidth - 2 * EDGE);
    const x = Math.min(Math.max(EDGE, r.left + r.width / 2 - w / 2), window.innerWidth - w - EDGE);
    const above = r.bottom + 110 > window.innerHeight && r.top > 110;
    setSpot({ x: Math.round(x), y: Math.round(above ? r.top - GAP : r.bottom + GAP), above, w });
  }, []);

  useEffect(() => {
    if (!open) return;
    place();
    const close = () => setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node | null;
      if (t && (ref.current?.contains(t) || (t as Element).closest?.(".tip-bubble"))) return;
      close();
    };
    window.addEventListener("scroll", close, { passive: true, capture: true });
    window.addEventListener("resize", close);
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      window.removeEventListener("scroll", close, { capture: true });
      window.removeEventListener("resize", close);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [open, place]);

  const toggle = (e: { stopPropagation: () => void; preventDefault: () => void }) => {
    e.stopPropagation();
    e.preventDefault();
    // A mouse already opened it by hovering: a click keeps it open instead of flickering it shut.
    setOpen((o) => (pointer.current === "mouse" ? true : !o));
  };
  const onKey = (e: ReactKeyEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      pointer.current = "key";
      toggle(e);
    }
  };
  const hover = (on: boolean) => (e: { pointerType: string }) => {
    if (e.pointerType === "mouse") setOpen(on);
  };
  const props = {
    ref,
    className: corner ? "tip-i" : "tip-term",
    "aria-label": corner ? `What is ${label}?` : undefined,
    "aria-describedby": open ? id : undefined,
    "aria-expanded": open,
    tabIndex: 0,
    role: "button" as const,
    onPointerDown: (e: { pointerType: string }) => void (pointer.current = e.pointerType),
    onPointerEnter: hover(true),
    onPointerLeave: hover(false),
    onClick: toggle,
    onKeyDown: onKey,
  };
  return (
    <>
      <span {...props}>{corner ? <span aria-hidden="true">i</span> : children}</span>
      {open &&
        spot &&
        createPortal(
          <span id={id} role="tooltip" className={`tip-bubble${spot.above ? " is-above" : ""}`} style={{ left: spot.x, top: spot.y, width: spot.w }}>
            {text}
          </span>,
          document.body,
        )}
    </>
  );
}
