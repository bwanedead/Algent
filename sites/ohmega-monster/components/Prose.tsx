import type { ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import XPostEmbed, { parseXStatusUrl } from "@/components/XPostEmbed";

// One markdown renderer for the whole site, so article prose and the source record behave
// identically. NOTE: no rehype-raw — raw HTML in content is never rendered, and markdown images
// become <img>, which is what keeps AI-generated SVG analytics from executing anything.
//
// X status embeds: when a paragraph is ONLY a link to an x.com/twitter.com status, render the
// public platform embed under it. No server setup — client iframe. Inline X links in mixed
// prose stay plain links (no embed spam).

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

/** If `children` is a single anchor (optionally wrapped) to an X status, return its parse. */
function soleXStatusFromChildren(children: ReactNode): ReturnType<typeof parseXStatusUrl> {
  const list = Array.isArray(children) ? children : [children];
  const meaningful = list.filter((c) => {
    if (c == null || c === false) return false;
    if (typeof c === "string") return c.trim().length > 0;
    return true;
  });
  if (meaningful.length !== 1) return null;

  const only = meaningful[0];
  // react-markdown passes the custom `a` element as a React element with props.href
  if (only && typeof only === "object" && "props" in only) {
    const props = (only as { props?: { href?: string; children?: ReactNode } }).props;
    const parsed = parseXStatusUrl(props?.href);
    if (parsed) return parsed;
  }

  // Fallback: bare URL text that remark didn't turn into a link
  const text = childToText(only).trim();
  return parseXStatusUrl(text);
}

const components = {
  // Every table gets a bounded, scrollable container. Analytics tables are often wide (a real one
  // shipped with seven columns), and a raw markdown table either overflows the page or squeezes
  // itself unreadable. Wrapping here — rather than asking the generator for narrower tables —
  // keeps the fix deterministic and applies to article tables too.
  table({ children, ...rest }: { children?: React.ReactNode }) {
    return (
      <div className="table-wrap">
        <table {...rest}>{children}</table>
      </div>
    );
  },

  // Outbound links open in a new tab: a reader checking a source (the receipts are *made* of
  // outbound links) should not lose the piece they were reading. Internal/anchor links stay
  // in-tab. rel=noopener/noreferrer is required with target=_blank — without it the opened page
  // gets window.opener access back into ours.
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

  // Sole-link paragraphs to an X status → embed. Mixed prose keeps normal paragraphs.
  p({ children, ...rest }: { children?: React.ReactNode }) {
    const x = soleXStatusFromChildren(children);
    if (x) {
      return (
        <>
          <p {...rest}>{children}</p>
          <XPostEmbed statusId={x.id} href={x.href} handle={x.handle} />
        </>
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
