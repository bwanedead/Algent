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
 * Visible X post card. Always shows a local chrome card (so the reader never only gets a
 * thin orange link). Optionally mounts the public platform iframe — sandboxed embeds often
 * fail silently; the card remains useful either way.
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
  const [showIframe, setShowIframe] = useState(true);

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

  const at = handle ? `@${handle}` : "on X";

  return (
    <figure className="x-post-embed">
      <div className="x-post-embed-card">
        <div className="x-post-embed-card-top">
          <span className="x-post-embed-mark" aria-hidden="true">
            𝕏
          </span>
          <div className="x-post-embed-meta">
            <span className="x-post-embed-handle">{at}</span>
            <span className="x-post-embed-sub">Post on X · pulse / open-source chatter</span>
          </div>
          <a
            className="x-post-embed-open"
            href={href}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open post ↗
          </a>
        </div>
        <p className="x-post-embed-note">
          Embedded for context — not a wire source. Status id{" "}
          <code className="x-post-embed-id">{statusId}</code>
        </p>
      </div>
      {showIframe ? (
        <iframe
          className="x-post-embed-frame"
          title={`Post on X ${at}`}
          src={src}
          loading="lazy"
          // no sandbox: X's public embed needs full script access; sandbox often yields a blank box
          referrerPolicy="no-referrer-when-downgrade"
          onError={() => setShowIframe(false)}
        />
      ) : null}
      <figcaption className="x-post-embed-cap">
        <a href={href} target="_blank" rel="noopener noreferrer">
          {handle ? `Post on X · @${handle}` : "Post on X"}
        </a>
        <span className="x-post-embed-hint">not a wire source</span>
      </figcaption>
    </figure>
  );
}
