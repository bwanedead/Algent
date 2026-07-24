"use client";

import { useEffect, useState } from "react";

/** Match x.com / twitter.com status URLs (with optional handle or /i/web/status/). */
export function parseXStatusUrl(
  href?: string | null,
): { id: string; handle?: string; href: string } | null {
  if (!href) return null;
  const m = href.match(
    /(?:https?:\/\/)?(?:(?:www|mobile)\.)?(?:twitter|x)\.com\/(?:([A-Za-z0-9_]{1,15})\/status\/(\d+)|i\/web\/status\/(\d+))/i,
  );
  if (!m) return null;
  const id = m[2] || m[3];
  if (!id) return null;
  const handle = m[1] || undefined;
  const canonical = handle
    ? `https://x.com/${handle}/status/${id}`
    : `https://x.com/i/web/status/${id}`;
  return { id, handle, href: canonical };
}

/**
 * Client-side X/Twitter status embed via the public platform iframe.
 * No backend, no API keys — just the status id in a sandboxed iframe.
 * Falls back to a plain outbound link if the iframe is blocked.
 */
export default function XPostEmbed({
  statusId,
  href,
  handle,
}: {
  statusId: string;
  href: string;
  handle?: string;
}) {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const apply = () => {
      const t = document.documentElement.getAttribute("data-theme");
      setTheme(t === "paper" ? "light" : "dark");
    };
    apply();
    const obs = new MutationObserver(apply);
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => obs.disconnect();
  }, []);

  const src =
    `https://platform.twitter.com/embed/Tweet.html?id=${encodeURIComponent(statusId)}` +
    `&theme=${theme}&dnt=true`;

  const label = handle ? `Post on X · @${handle}` : "Post on X";

  return (
    <figure className="x-post-embed">
      <iframe
        className="x-post-embed-frame"
        title={label}
        src={src}
        loading="lazy"
        referrerPolicy="no-referrer"
        // sandbox keeps third-party script contained; allow-scripts/same-origin needed for embed UI
        sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
      />
      <figcaption className="x-post-embed-cap">
        <span className="x-post-embed-mark">X</span>
        <a href={href} target="_blank" rel="noopener noreferrer">
          {label}
        </a>
        <span className="x-post-embed-hint">embedded post · not a wire source</span>
      </figcaption>
    </figure>
  );
}
