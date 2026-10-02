"use client";

// THE detail-on-demand primitive. A trigger button opens a dialog layered over the page (position:
// fixed, anchored under the trigger, flipped above when there is no room, clamped to the viewport;
// a bottom sheet with a scrim under 640px). The page never reflows. Esc, × and outside click close it;
// focus moves to × on open and back to the trigger on close. One popover is open site-wide at a time
// (a window event), and `id` makes /page#<id> open it on load and on hashchange.

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";

import "./popover.css";

// detail = { uid, keep }: the popover that just opened, and the ancestors it was opened from. A popover
// opened from inside another one STACKS on it (its parent stays open beneath); any other closes.
const OPENED = "ohmega:popover-open";
type Opened = { uid: string; keep: string[] };
const PHONE = "(max-width: 639px)";
const GAP = 6;
const EDGE = 8;

function hashId(): string {
  const h = window.location.hash.slice(1);
  try {
    return decodeURIComponent(h);
  } catch {
    return h;
  }
}

type PanelProps = { label: string; wide: boolean; anchor: RefObject<HTMLButtonElement>; onClose: (restoreFocus: boolean) => void; children: ReactNode; uid: string; parent: string };

/** Mounted only while open, so it is client-only (layout effects, DOM measuring) by construction. */
function Panel({ label, wide, anchor, onClose, children, uid, parent }: PanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const placed = useRef("");

  // Anchored placement, written only when it changes. Cheap enough to run every frame, which makes the
  // panel follow its trigger through scroll, resize, re-sorting and late layout shifts alike.
  const place = useCallback(() => {
    const panel = panelRef.current;
    const trigger = anchor.current;
    if (!panel || !trigger) return;
    let key = "sheet";
    let x = 0;
    let y = 0;
    if (!window.matchMedia(PHONE).matches) {
      const r = trigger.getBoundingClientRect();
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const pw = panel.offsetWidth;
      const ph = panel.offsetHeight;
      x = Math.round(Math.min(Math.max(EDGE, r.left), Math.max(EDGE, vw - pw - EDGE)));
      y = r.bottom + GAP;
      if (y + ph > vh - EDGE) y = r.top - ph - GAP; // no room below: flip above
      if (y < EDGE) y = Math.max(EDGE, vh - ph - EDGE); // no room either way: pin inside the viewport
      y = Math.round(y);
      key = `${x},${y}`;
    }
    if (key === placed.current) return;
    placed.current = key;
    panel.style.setProperty("--pop-x", `${x}px`);
    panel.style.setProperty("--pop-y", `${y}px`);
  }, [anchor]);

  useLayoutEffect(() => {
    place();
    if (panelRef.current) panelRef.current.dataset.ready = "1";
    closeRef.current?.focus({ preventScroll: true });
  }, [place]);

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      place();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    // Panels portal into <body> in opening order, so the last one in the document is the topmost.
    const isTop = () => {
      const all = document.querySelectorAll(".pop-panel");
      return all.length === 0 || all[all.length - 1] === panelRef.current;
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isTop()) onClose(true); // Esc peels one layer at a time
    };
    const onDown = (e: PointerEvent) => {
      const t = e.target as Element | null;
      if (!t || panelRef.current?.contains(t) || anchor.current?.contains(t)) return; // the trigger toggles itself
      if (t.closest?.(".pop-panel")) return; // a click inside a stacked popover is not "outside" this one
      onClose(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [place, onClose, anchor]);

  return (
    <>
      <div className="pop-scrim" aria-hidden="true" />
      <div ref={panelRef} className="pop-panel" role="dialog" aria-modal="false" aria-label={label} tabIndex={-1} data-wide={wide ? "" : undefined} data-pop-uid={uid} data-pop-parent={parent || undefined}>
        <div className="pop-scroll">{children}</div>
        <button ref={closeRef} type="button" className="pop-x" onClick={() => onClose(true)} aria-label="Close">
          ×
        </button>
      </div>
    </>
  );
}

export default function Popover({
  label,
  trigger,
  children,
  triggerClassName,
  id,
  wide = false,
}: {
  /** Accessible name of the dialog. */
  label: string;
  /** What the button shows (phrasing content only: it lives inside a <button>). */
  trigger: ReactNode;
  children: ReactNode;
  triggerClassName?: string;
  /** DOM id of the trigger; /page#<id> opens this popover on load and hashchange. */
  id?: string;
  /** ~640px panel instead of ~420px. */
  wide?: boolean;
}) {
  const uid = useId();
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const parentRef = useRef("");

  const show = useCallback(() => {
    // Opened from inside another popover's panel? Then that popover (and its own ancestors) stay open.
    const keep: string[] = [];
    let el: Element | null | undefined = btnRef.current?.closest(".pop-panel");
    while (el) {
      const owner = (el as HTMLElement).dataset.popUid;
      if (owner) keep.push(owner);
      el = (el as HTMLElement).dataset.popParent
        ? document.querySelector(`.pop-panel[data-pop-uid="${CSS.escape((el as HTMLElement).dataset.popParent || "")}"]`)
        : null;
    }
    parentRef.current = keep[0] ?? "";
    window.dispatchEvent(new CustomEvent<Opened>(OPENED, { detail: { uid, keep } }));
    setOpen(true);
  }, [uid]);

  const close = useCallback(
    (restoreFocus: boolean) => {
      setOpen(false);
      if (id && hashId() === id) window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
      if (restoreFocus) btnRef.current?.focus({ preventScroll: true });
    },
    [id],
  );

  useEffect(() => {
    const onOther = (e: Event) => {
      const { uid: opened, keep } = (e as CustomEvent<Opened>).detail;
      if (opened !== uid && !keep.includes(uid)) setOpen(false);
    };
    window.addEventListener(OPENED, onOther);
    return () => window.removeEventListener(OPENED, onOther);
  }, [uid]);

  useEffect(() => {
    if (!id) return;
    let initial = true;
    const sync = () => {
      if (hashId() !== id) return;
      show();
      // The browser's own hash scroll can land before client-side re-ordering; settle once layout has.
      if (initial) requestAnimationFrame(() => btnRef.current?.scrollIntoView({ block: "center" }));
    };
    sync();
    initial = false;
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, [id, show]);

  return (
    <>
      <button ref={btnRef} type="button" id={id} className={triggerClassName} aria-haspopup="dialog" aria-expanded={open} onClick={() => (open ? close(true) : show())}>
        {trigger}
      </button>
      {open &&
        createPortal(
          <Panel label={label} wide={wide} anchor={btnRef} onClose={close} uid={uid} parent={parentRef.current}>
            {children}
          </Panel>,
          document.body,
        )}
    </>
  );
}
