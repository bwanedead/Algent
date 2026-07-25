"use client";

// Client boundary: embeds XPostEmbed (client) under sole-link status URLs. Must be a client
// module — a server Prose that imports a client child broke static export with
// "TypeError: rK is not a function" during prerender (Vercel production deploys failed).

import type { ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import ArticleImage from "@/components/ArticleImage";
import XPostEmbed, { parseXStatusUrl } from "@/components/XPostEmbed";

// One markdown renderer for the whole site, so article prose and the source record behave
// identically. NOTE: no rehype-raw — raw HTML in content is never rendered, and markdown images
// become <img>, which is what keeps AI-generated SVG analytics from executing anything.
//
// X status embeds: when a paragraph is effectively only a link to an x.com/twitter.com status,
// render a visible post card. Inline X links inside mixed prose stay plain links.

function childToText(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(childToText).join("");
  if (typeof node === "object" && node !== null && "props" in node) {
    const el = node as { props?: { children?: ReactNode } };
    return childToText(el.props?.children);
  }
  return "";
}

function flatten(node: ReactNode): ReactNode[] {
  if (node == null || node === false) return [];
  if (Array.isArray(node)) return node.flatMap(flatten);
  return [node];
}

/** True if this React node is an element (host or custom) with an href prop. */
function elementHref(node: ReactNode): string | undefined {
  if (!node || typeof node !== "object" || !("props" in node)) return undefined;
  const href = (node as { props?: { href?: string } }).props?.href;
  return typeof href === "string" ? href : undefined;
}

/**
 * If the paragraph is effectively a single X status link (plus optional whitespace), return it.
 * Handles react-markdown's custom `a` output and bare URL text.
 */
function soleXStatusFromChildren(children: ReactNode): ReturnType<typeof parseXStatusUrl> {
  const nodes = flatten(children).filter((c) => {
    if (c == null || c === false) return false;
    if (typeof c === "string") return c.trim().length > 0;
    return true;
  });
  if (nodes.length === 0) return null;

  // Single link element
  if (nodes.length === 1) {
    const only = nodes[0];
    const href = elementHref(only);
    if (href) return parseXStatusUrl(href);
    return parseXStatusUrl(childToText(only).trim());
  }

  // One link + only whitespace-ish leftovers already filtered; reject multi-content paragraphs
  const hrefs = nodes.map(elementHref).filter(Boolean) as string[];
  if (hrefs.length === 1 && nodes.every((n) => elementHref(n) || (typeof n === "string" && !n.trim()))) {
    return parseXStatusUrl(hrefs[0]);
  }
  return null;
}

const components = {
  // Charts and maps carry small labels; at body width they are borderline and on a phone
  // unreadable. Tap/click opens them full-screen (see ArticleImage).
  img({ src, alt }: { src?: string; alt?: string }) {
    return <ArticleImage src={src} alt={alt} />;
  },

  table({ children, ...rest }: { children?: React.ReactNode }) {
    return (
      <div className="table-wrap">
        <table {...rest}>{children}</table>
      </div>
    );
  },

  a({ href, children, ...rest }: { href?: string; children?: React.ReactNode }) {
    const external = !!href && /^https?:\/\//i.test(href);
    return external ? (
      <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
        {children}
      </a>
    ) : (
      <a href={href} {...rest}>
        {children}
      </a>
    );
  },

  // Sole-link X status → card (replace the thin paragraph link, don't leave only an orange line).
  p({ children, ...rest }: { children?: React.ReactNode }) {
    const x = soleXStatusFromChildren(children);
    if (x) {
      return (
        <div className="x-post-embed-wrap" {...rest}>
          <XPostEmbed statusId={x.id} href={x.href} handle={x.handle} />
        </div>
      );
    }
    return <p {...rest}>{children}</p>;
  },
};

export default function Prose({ children }: { children: string }) {
  return (
    <Markdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </Markdown>
  );
}
