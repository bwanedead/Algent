"use client";

// Figures in an article are charts and maps — dense things with axes, labels and place
// names. At body width those labels are often at the edge of legible, and on a phone they
// are not legible at all, so a reader's instinct is to tap the image expecting it to open.
// It did nothing. This makes that instinct work.
//
// Deliberately NOT applied to the index thumbnails: there, a tap means "open the article",
// and hijacking it to show a bigger picture would be worse than the small thumbnail.

import { useCallback, useEffect, useState } from "react";

export default function ArticleImage({ src, alt }: { src?: string; alt?: string }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    // Don't let the page scroll behind the overlay.
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, close]);

  if (!src) return null;

  return (
    <>
      {/* A button, not a bare img with onClick — this is an interactive control, and it has
          to be reachable by keyboard and announce itself to a screen reader. */}
      <button
        type="button"
        className="figure-zoom"
        onClick={() => setOpen(true)}
        aria-label={alt ? `Enlarge: ${alt}` : "Enlarge figure"}
      >
        <img src={src} alt={alt ?? ""} loading="lazy" />
      </button>

      {open && (
        <div
          className="lightbox"
          role="dialog"
          aria-modal="true"
          aria-label={alt || "Enlarged figure"}
          onClick={close}
        >
          <button type="button" className="lightbox-close" onClick={close} aria-label="Close">
            ×
          </button>
          {/* Stop propagation so clicking the image itself doesn't dismiss it mid-pinch-zoom. */}
          <img src={src} alt={alt ?? ""} onClick={(e) => e.stopPropagation()} />
        </div>
      )}
    </>
  );
}
