"use client";

import { useEffect, useId, useRef, useState } from "react";

type Props = {
  url: string;
  title: string;
  dek?: string;
  className?: string;
};

function sharePayload(title: string, url: string): string {
  return `Check out this article from Ohmega Monster:\n${title}\n${url}`;
}

async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
}

/**
 * Minimal share: icon opens a small panel with the link and one Copy action.
 * Paste payload is a short Ohmega Monster line + title + URL — no system share sheet.
 */
export default function ShareButton({ url, title, className }: Props) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<"idle" | "copied" | "failed">("idle");
  const rootRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    function onPointer(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (!open) setStatus("idle");
  }, [open]);

  async function onCopy(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    try {
      await copyText(sharePayload(title, url));
      setStatus("copied");
      window.setTimeout(() => setStatus("idle"), 2000);
    } catch {
      setStatus("failed");
      window.setTimeout(() => setStatus("idle"), 2500);
    }
  }

  function toggle(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setOpen((v) => !v);
  }

  const copyLabel =
    status === "copied" ? "Copied"
    : status === "failed" ? "Copy failed"
    : "Copy";

  return (
    <div
      ref={rootRef}
      className={className ? `share ${className}` : "share"}
    >
      <button
        type="button"
        className="share-trigger"
        aria-label="Share this article"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={toggle}
      >
        <svg
          className="share-icon"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.85"
          strokeLinecap="square"
          strokeLinejoin="miter"
          aria-hidden="true"
        >
          <circle cx="18" cy="5" r="2.25" />
          <circle cx="6" cy="12" r="2.25" />
          <circle cx="18" cy="19" r="2.25" />
          <path d="M8.2 10.9 15.8 6.1M8.2 13.1 15.8 17.9" />
        </svg>
        <span className="share-trigger-label">Share</span>
      </button>

      {open ? (
        <div
          id={panelId}
          className="share-panel"
          role="dialog"
          aria-label="Copy link"
          onClick={(e) => e.stopPropagation()}
        >
          <p className="share-hint">Copy a link to share</p>
          <input
            className="share-url"
            type="text"
            readOnly
            value={url}
            aria-label="Article link"
            onFocus={(e) => e.currentTarget.select()}
          />
          <div className="share-actions">
            <button type="button" className="share-copy" onClick={onCopy}>
              {copyLabel}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
