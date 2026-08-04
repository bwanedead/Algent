"use client";

import { useState } from "react";

type Props = {
  url: string;
  title: string;
  dek?: string;
  className?: string;
};

/**
 * Standard article share: system share sheet when the browser supports it (carries
 * title + URL so messengers/OS can show the Open Graph preview), otherwise copy a
 * short "Check out this article" blurb + link to the clipboard.
 */
export default function ShareButton({ url, title, dek, className }: Props) {
  const [status, setStatus] = useState<"idle" | "copied" | "shared" | "failed">("idle");

  async function share(e: React.MouseEvent) {
    // Index cards wrap the row in a Link — don't navigate when sharing.
    e.preventDefault();
    e.stopPropagation();
    const text = `Check out this article: ${title}`;
    try {
      if (typeof navigator !== "undefined" && typeof navigator.share === "function") {
        await navigator.share({
          title,
          text: dek?.trim() ? `${text}\n${dek.trim()}` : text,
          url,
        });
        setStatus("shared");
        window.setTimeout(() => setStatus("idle"), 2000);
        return;
      }
      const payload = `${text}\n${url}`;
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(payload);
      } else {
        const ta = document.createElement("textarea");
        ta.value = payload;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setStatus("copied");
      window.setTimeout(() => setStatus("idle"), 2000);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setStatus("failed");
      window.setTimeout(() => setStatus("idle"), 2500);
    }
  }

  const label =
    status === "copied" ? "Link copied"
    : status === "shared" ? "Shared"
    : status === "failed" ? "Share failed"
    : "Share";

  return (
    <button
      type="button"
      className={className ? `share-button ${className}` : "share-button"}
      onClick={share}
      aria-label={status === "idle" ? "Share this article" : label}
    >
      {label}
    </button>
  );
}
